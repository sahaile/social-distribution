import { generateCommonmarkHtml } from './renderer.min.js'

function getCSRFToken () {
  // First try to get it from the meta tag (if server provides it)
  const metaToken = document.querySelector('meta[name="csrf-token"]')
  if (metaToken) {
    const token = metaToken.getAttribute('content')
    return token
  }

  const decodedCookie = decodeURIComponent(document.cookie)
  const ca = decodedCookie.split(';')

  // Get node name from server-provided variable
  const nodeName = window.currentNodeName || 'default'

  // Now look for the CSRF token for this specific node
  const expectedCookieName = `csrftoken_${nodeName}`

  for (let i = 0; i < ca.length; i++) {
    const c = ca[i].trim()
    if (c.indexOf(expectedCookieName + '=') === 0) {
      const token = c.substring(expectedCookieName.length + 1)
      return token
    }
  }

  // Fallback: use any csrftoken_* cookie if node-specific one not found
  for (let i = 0; i < ca.length; i++) {
    const c = ca[i].trim()
    if (c.indexOf('csrftoken_') === 0) {
      const equalsIndex = c.indexOf('=')
      if (equalsIndex !== -1) {
        const token = c.substring(equalsIndex + 1)
        return token
      }
    }
  }
  return ''
}

function fqidToLocalEntryUrl (entryFqid) {
  try {
    const decodedFqid = decodeURIComponent(entryFqid)
    const url = new URL(decodedFqid)
    const pathParts = url.pathname.replace(/^\/+|\/+$/g, '').split('/')

    const entrySerial = pathParts[pathParts.length - 1]
    const authorSerial = pathParts[pathParts.length - 3]

    if (!entrySerial || !authorSerial) {
      return entryFqid
    }

    const baseUrl = window.location.origin
    return `${baseUrl}/authors/${authorSerial}/entries/${entrySerial}/`
  } catch (error) {
    console.warn('Failed to parse entry FQID:', entryFqid, error)
    return entryFqid
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const tweetList = document.querySelector('.tweet-list')
  tweetList.innerHTML = '<div>Loading…</div>'
  let currentAuthor = null

  async function fetchAllAuthors () {
    let allAuthors = []
    let page = 1
    let hasMore = true

    while (hasMore) {
      try {
        const response = await fetch(`/api/authors/?page=${page}`)
        if (!response.ok) {
          throw new Error(`Failed to fetch authors page ${page}: ${response.statusText}`)
        }

        const data = await response.json()
        const authors = data.authors || []

        if (authors.length === 0) {
          hasMore = false
        } else {
          allAuthors = allAuthors.concat(authors)
          page++
        }
      } catch (error) {
        console.error(`Error fetching authors page ${page}:`, error)
        hasMore = false
      }
    }

    return allAuthors
  }

  function loadSingleEntryForUnauthenticated (authorSerial, entrySerial) {
    fetch(`/api/authors/${authorSerial}/entries/${entrySerial}/`)
      .then(response => {
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('Entry not found')
          } else if (response.status === 403) {
            throw new Error('Access denied - login required')
          } else {
            throw new Error(`Failed to fetch entry: ${response.status} ${response.statusText}`)
          }
        }
        return response.json()
      })
      .then(entryData => {
        // Ensure _author property exists for renderEntries compatibility
        if (entryData.author && !entryData._author) {
          entryData._author = entryData.author
        }
        renderEntries([entryData])
        hideAuthenticatedOnlyElements()
      })
      .catch(error => {
        console.error('Failed to load entry:', error)
        if (error.message.includes('Access denied')) {
          tweetList.innerHTML = '<div style="color:red;">This entry requires authentication. <a href="/login/">Login</a> to continue.</div>'
        } else if (error.message.includes('not found')) {
          tweetList.innerHTML = '<div style="color:red;">Entry not found.</div>'
        } else {
          tweetList.innerHTML = '<div style="color:red;">Error loading entry: ' + error.message + '</div>'
        }
      })
  }

  function loadPublicEntriesForUnauthenticated () {
    fetch('/api/entries/')
      .then(response => {
        if (!response.ok) {
          throw new Error(`Failed to fetch public entries: ${response.status} ${response.statusText}`)
        }
        return response.json()
      })
      .then(data => {
        const entries = data.src || []

        // Ensure _author property exists for renderEntries compatibility
        entries.forEach(entry => {
          if (entry.author && !entry._author) {
            entry._author = entry.author
          }
        })

        if (entries.length === 0) {
          tweetList.innerHTML = '<div style="color:#999;">No public entries found.</div>'
        } else {
          renderEntries(entries)
        }
        hideAuthenticatedOnlyElements()
      })
      .catch(error => {
        console.error('Failed to load public entries:', error)
        tweetList.innerHTML = '<div style="color:red;">Error loading public content: ' + error.message + '</div>'
      })
  }

  function hideAuthenticatedOnlyElements () {
    // Hide profile sections, post form, and other authenticated-only UI elements
    const profileSection = document.querySelector('.profile-section')
    const postSection = document.querySelector('.post-tweet')
    const rightSection = document.querySelector('.right-section')

    if (profileSection) profileSection.style.display = 'none'
    if (postSection) postSection.style.display = 'none'
    if (rightSection) rightSection.style.display = 'none'
  }

  function loadGlobalFeed () {
    const currentUserSerial = window.currentUserSerial
    const isAuthenticated = currentUserSerial && currentUserSerial !== 'None' && currentUserSerial !== ''

    if (!isAuthenticated) {
      // Handle unauthenticated users - only show specific entry if requested
      const currentEntrySerial = window.currentEntrySerial
      const currentEntryAuthorSerial = window.currentEntryAuthorSerial

      if (currentEntrySerial && currentEntryAuthorSerial) {
        // Show specific entry for unauthenticated user
        loadSingleEntryForUnauthenticated(currentEntryAuthorSerial, currentEntrySerial)
      } else {
        // Show public entries only
        loadPublicEntriesForUnauthenticated()
      }
      return
    }

    // Authenticated user flow
    fetchAllAuthors()
      .then((authors) => {
        if (!authors.length) {
          tweetList.innerHTML =
            '<div style="color:#999;">No authors found on this server.</div>'
          return
        }
        currentAuthor = authors.find((author) => {
          const authorSerial = getAuthorSerial(author)
          return authorSerial === currentUserSerial
        })
        if (!currentAuthor) {
          console.error('Could not find current user in author list.')
          return
        }
        updateProfileUI(currentAuthor)
        loadFriendRequests(currentAuthor)

        loadEntryForm(currentAuthor, authors)
        loadFeedEntries(authors, '/api/stream/')
      })
      .catch((error) => {
        console.error('Failed to fetch authors:', error)
        tweetList.innerHTML =
          '<div style="color:red;">Error loading authors.</div>'
      })
  }

  function loadFeedEntries (authors, endpointUrl) {
    new Promise((resolve, reject) => {
      const currentEntrySerial = window.currentEntrySerial
      const currentEntryAuthorSerial = window.currentEntryAuthorSerial
      if (currentEntrySerial) { // If this is supposed to be an entry-specific page
        console.log(currentEntrySerial)
        const currentEntryAuthor = authors.find((author) => {
          const authorSerial = getAuthorSerial(author)
          return authorSerial === currentEntryAuthorSerial
        })

        const entryPromise = fetch(`/api/authors/${currentEntryAuthorSerial}/entries/${currentEntrySerial}`)
          .then((res) => (res.ok ? res.json() : null))
          .then((entryData) => {
            if (!entryData) return []
            entryData._author = currentEntryAuthor
            return [entryData]
          })
          .catch(error => reject(error))

        resolve(entryPromise)
      } else {
        const feedPromise = fetch(endpointUrl)
          .then(res => (res.ok ? res.json() : { src: [] }))
          .then(data => data.src)

        resolve(feedPromise)
      }
    }).then((allEntries) => {
      console.log('After promise all')
      // This check is needed in case the previous .then returned early
      if (!allEntries) return

      if (!allEntries.length) {
        tweetList.innerHTML =
            '<div style="color:#999;">No entries found.</div>'
        return
      }

      allEntries.forEach(entry => {
        if (entry.author && !entry._author) {
          entry._author = entry.author
        }
      })

      allEntries.sort(
        (a, b) =>
          new Date(b.published || b.created_at) -
            new Date(a.published || a.created_at)
      )

      renderEntries(allEntries)
    })
      .catch((error) => {
        console.error('Failed to load the global feed:', error)
        tweetList.innerHTML =
          '<div style="color:red;">Error loading feed.</div>'
      })
  }

  function loadEntryForm (currentAuthor, authors) {
    // Replace content select with clone to remove eventlisteners.
    let entryFormContentTypeSelect = document.querySelector('#post_entry_content_type--select')
    const currContentType = entryFormContentTypeSelect.value
    entryFormContentTypeSelect.replaceWith(entryFormContentTypeSelect.cloneNode(true))
    entryFormContentTypeSelect = document.querySelector('#post_entry_content_type--select')
    entryFormContentTypeSelect.value = currContentType

    // Replace entry form submit button with clone to remove eventlisteners.
    let entryFormSubmitButton = document.querySelector('#post_entry_actions--div button')
    entryFormSubmitButton.replaceWith(entryFormSubmitButton.cloneNode(true))
    entryFormSubmitButton = document.querySelector('#post_entry_actions--div button')

    const entryFormTitleInput = document.querySelector('#post_entry_title--input')
    const entryFormDescriptionInput = document.querySelector('#post_entry_description--input')
    const entryFormContentTextInput = document.querySelector('#post_entry_content_text--input')
    const entryFormContentFileInput = document.querySelector('#post_entry_content_file--input')
    const entryFormVisibilitySelect = document.querySelector('#post_entry_visibility--select')

    const entryFormContentType = entryFormContentTypeSelect.value
    switch (entryFormContentType) {
      case 'text/plain':
      case 'text/markdown':
        entryFormContentTextInput.hidden = false
        entryFormContentFileInput.hidden = true
        break
      case 'image':
        entryFormContentTextInput.hidden = true
        entryFormContentFileInput.hidden = false
        break
      default:
        console.error(`Unknown entry form content selected: ${entryFormContentType}`)
    }

    entryFormContentTypeSelect.addEventListener('change', e => {
      loadEntryForm(currentAuthor, authors)
    })

    entryFormSubmitButton.addEventListener('click', e => {
      e.preventDefault()
      console.log('Entry form submit button clicked!')

      new Promise((resolve, reject) => {
        switch (entryFormContentType) {
          case 'text/plain':
          case 'text/markdown':
            resolve({
              title: entryFormTitleInput.value,
              description: entryFormDescriptionInput.value,
              visibility: entryFormVisibilitySelect.value,
              contentType: entryFormContentTypeSelect.value,
              content: entryFormContentTextInput.value
            })
            break
          case 'image': {
            const file = entryFormContentFileInput.files[0]
            const reader = new FileReader()
            reader.readAsDataURL(file)

            reader.onload = () => {
              const encodedImage = reader.result.split('base64,')[1]
              console.log(reader.result.split('base64,'))

              let imageContentType
              if (encodedImage.startsWith('/9j/')) {
                imageContentType = 'image/jpeg;base64'
              } else if (encodedImage.startsWith('iVBORw0KGgo')) {
                imageContentType = 'image/png;base64'
              } else {
                imageContentType = 'application/base64'
              }
              resolve({
                title: entryFormTitleInput.value,
                description: entryFormDescriptionInput.value,
                visibility: entryFormVisibilitySelect.value,
                contentType: imageContentType,
                content: encodedImage
              })
            }
            reader.onerror = reject
            break
          }
          default:
            reject(new Error(`Unknown entry form content selected: ${entryFormContentType}`))
        }
      }).then(requestBody => {
        fetch(`/api/authors/${getAuthorSerial(currentAuthor)}/entries/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCSRFToken(),
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        }).then(res => {
          if (res.status === 201) {
            loadFeedEntries(authors, '/api/stream/')
          } else {
            console.debug(res)
            alert('Could not create a post at the moment. Please try again later!')
          }
        })
      }).catch(error => {
        console.error(`Error while in entry form: ${error}`)
      })
    })
  }

  function updateProfileUI (author) {
    if (!author) return
    const authorSerial = getAuthorSerial(author)

    // find existing profile-name element
    let nameEl = document.querySelector(
      '.profile-section .profile-display-name'
    )

    // if it doesn’t exist or isn’t a div, recreate it
    if (!nameEl || nameEl.tagName.toLowerCase() !== 'div') {
      if (nameEl) nameEl.remove()

      nameEl = document.createElement('div')
      nameEl.className = 'profile-display-name'
      nameEl.style.fontWeight = 'bold'
      nameEl.style.marginTop = '10px'
      nameEl.style.cursor = 'pointer' // show hand cursor
      nameEl.addEventListener('click', () => {
        window.location.href = `/authors/${authorSerial}/`
      })

      document
        .querySelector('.profile-section')
        .insertBefore(nameEl, document.querySelector('.profile-info'))
    }

    nameEl.textContent = author.displayName

    const profilePicElement = document.querySelector('.profile-pic')
    if (author.profileImage) {
      profilePicElement.src = author.profileImage
      profilePicElement.onerror = function () {
        this.src = '/static/images/defaultprofile.webp'
      }
    } else {
      profilePicElement.src = '/static/images/defaultprofile.webp'
    }

    if (authorSerial) {
      document.getElementById('following-count').textContent =
        author.following_count ?? 0
      document.getElementById('followers-count').textContent =
        author.followers_count ?? 0
      document.getElementById('friends-count').textContent =
        author.friends_count ?? 0
      document.getElementById(
        'following-link'
      ).href = `/authors/${authorSerial}/following/`
      document.getElementById(
        'followers-link'
      ).href = `/authors/${authorSerial}/followers/`
      document.getElementById(
        'friends-link'
      ).href = `/authors/${authorSerial}/friends/`
    }

    document.getElementById('edit-link').href = `/authors/${authorSerial}/edit/`

    if (author.github) {
      let ghLink = author.github
      if (!ghLink.startsWith('http')) {
        ghLink = 'https://github.com/' + ghLink
      }
      const githubLinkElement = document.querySelector('.github-link')
      githubLinkElement.href = ghLink
      githubLinkElement.childNodes[2].nodeValue =
        ' ' + author.github.split('/').pop()
    }
  }

  function renderEntries (entries) {
    tweetList.innerHTML = ''
    entries.forEach((entry) => {
      console.log(entry)
      const tweet = document.createElement('article')
      tweet.className = 'tweet'
      const webUrl = entry._author.web
      const authorPicLink = document.createElement('a')
      authorPicLink.href = webUrl
      authorPicLink.style.display = 'inline-block'
      const authorPic = document.createElement('img')
      authorPic.className = 'profile-pic'
      authorPic.style.width = '36px'
      authorPic.style.height = '36px'
      authorPic.alt = 'User Pic'
      if (entry._author.profileImage) {
        authorPic.src = entry._author.profileImage
        authorPic.onerror = function () {
          this.src = '/static/images/defaultprofile.webp'
        }
      } else {
        authorPic.src = '/static/images/defaultprofile.webp'
      }
      authorPicLink.appendChild(authorPic)
      const authorNameLink = document.createElement('a')
      authorNameLink.href = webUrl
      authorNameLink.style.textDecoration = 'none'
      authorNameLink.style.color = 'inherit'
      const strong = document.createElement('strong')
      strong.textContent = getAuthorName(entry._author)
      authorNameLink.appendChild(strong)
      const uuidSpan = document.createElement('span')
      uuidSpan.style.fontSize = '13px'
      uuidSpan.style.color = '#aaa'
      uuidSpan.textContent = `@${getAuthorSerial(entry._author).substring(
        0,
        8
      )}... • ${timeAgo(entry.published)}`
      const authorRow = document.createElement('div')
      authorRow.style.display = 'flex'
      authorRow.style.alignItems = 'center'
      authorRow.style.gap = '10px'
      authorRow.appendChild(authorPicLink)
      authorRow.appendChild(authorNameLink)
      authorRow.appendChild(uuidSpan)

      const entryContent = document.createElement('div')
      entryContent.className = 'tweet-content'

      function renderEntryContent () {
        entryContent.style.margin = '10px 0 6px 0'
        if (entry.title) {
          const title = document.createElement('a')
          title.style.fontWeight = '600'
          title.textContent = entry.title
          title.href = fqidToLocalEntryUrl(entry.id)
          entryContent.appendChild(title)
        }
        switch (entry.contentType) {
          case 'image/png;base64':
          case 'image/jpeg;base64':
          case 'application/base64': {
            const entryImage = document.createElement('img')
            entryImage.className = 'tweet-image'
            const basePath = window.location.origin
            entryImage.src = `${basePath}/api/entries/${encodeURIComponent(entry.id)}/image?t=${new Date().getTime()}`
            entryImage.onerror = function () {
              this.style.display = 'none'
              const placeholder = document.createElement('div')
              placeholder.className = 'image-placeholder'
              placeholder.style.cssText = `
                background-color: #f0f0f0;
                border: 2px dashed #ccc;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                color: #666;
                font-style: italic;
                margin: 10px 0;
              `
              placeholder.textContent = 'Image not available'
              this.parentNode.insertBefore(placeholder, this)
            }
            entryContent.appendChild(entryImage)
            break
          }
          case 'text/plain': {
            const para = document.createElement('p')
            para.textContent = (entry.content || '').substring(0, 280)
            entryContent.appendChild(para)
            break
          }
          case 'text/markdown': {
            const markdownDiv = document.createElement('div')
            markdownDiv.innerHTML = generateCommonmarkHtml(entry.content || '')
            entryContent.appendChild(markdownDiv)
            entryContent.style.display = 'block'
            break
          }
        }
      }
      renderEntryContent()

      const footer = document.createElement('div')
      footer.style.display = 'flex'
      footer.style.gap = '18px'
      footer.style.fontSize = '14px'
      footer.style.alignItems = 'center'
      const likeBtn = document.createElement('button')
      likeBtn.innerHTML = '❤️ Like'
      likeBtn.style.background = 'none'
      likeBtn.style.border = 'none'
      likeBtn.style.cursor = 'pointer'
      likeBtn.style.fontSize = '15px'
      likeBtn.style.display = 'flex'
      likeBtn.style.alignItems = 'center'
      likeBtn.style.gap = '4px'

      const likeCountSpan = document.createElement('span')
      likeCountSpan.style.marginLeft = '6px'
      likeCountSpan.style.color = '#e0245e'
      likeCountSpan.style.fontWeight = 'bold'

      const entryUUID = extractEntryUUID(entry)
      const authorSerial = getAuthorSerial(entry._author)

      //* **Documentation**
      // ENDPOINT:
      // POST /api/authors/{author_id}/entries/{entry_id}/likes/

      // json:
      // {
      //   "Content-Type": "application/json",
      //   "X-CSRFToken": "<token>"
      // }

      // Purpose: Records entries liked by the user
      // Response: 201
      // Example:
      // | Field         | Type   | Example Value                        | Purpose/When to Use                |
      // |---------------|--------|--------------------------------------|------------------------------------|
      // | author_id     | string | "1234abcd"                           | The serial/UUID of the author of the entry |
      // | entry_id      | string | "5678efgh"                             he UUID of the entry being liked          |
      // Check if current author has already liked this entry
      fetch(`/api/authors/${authorSerial}/entries/${entryUUID}/likes/`)
        .then((res) => res.json())
        .then((data) => {
          let liked = false
          let likeCount = 0
          // Finding which posts the author liked
          if (data && data.src) {
            likeCount = data.src.length
            // for the posts with likes, set liked to be true
            liked = data.src.some((like) => {
              return getAuthorSerial(like.author) === getAuthorSerial(currentAuthor)
            })
          }
          if (liked) { // If liked, set new HTML
            likeBtn.textContent = `❤️ Liked (${likeCount})`
            likeBtn.disabled = true
          } else { // Add listener if not
            likeBtn.disabled = false
            likeBtn.textContent = `❤️ Like (${likeCount})`
            likeBtn.addEventListener('click', (e) => {
              fetch(`/api/authors/${authorSerial}/entries/${entryUUID}/likes/`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'X-CSRFToken': getCSRFToken()
                },
                credentials: 'include'
              })
                // promise here does the change "live"
                .then((res) => {
                  if (res.ok) {
                    likeCount += 1
                    likeBtn.textContent = `❤️ Liked (${likeCount})`
                    likeBtn.disabled = true
                  } else {
                    alert('Failed to like entry.')
                  }
                })
            }, { once: true })
          }
        })
      footer.appendChild(likeBtn)

      const replyBtn = document.createElement('button')
      replyBtn.innerHTML = '💬 Reply'
      replyBtn.style.background = 'none'
      replyBtn.style.border = 'none'
      replyBtn.style.cursor = 'pointer'
      replyBtn.style.fontSize = '15px'
      replyBtn.style.display = 'flex'
      replyBtn.style.alignItems = 'center'
      replyBtn.style.gap = '4px'
      const replyBox = document.createElement('div')
      replyBox.style.display = 'none'
      replyBox.style.marginTop = '10px'
      const replyList = document.createElement('div')
      replyList.className = 'reply-list'
      const replyForm = document.createElement('form')
      replyForm.className = 'reply-form'
      replyForm.style.display = 'flex'
      replyForm.style.flexDirection = 'column'
      replyForm.style.gap = '8px'
      replyForm.innerHTML = `
        <textarea rows="2" placeholder="Write a reply..."></textarea>
        <div>
          <button type="submit">Reply</button>
          <button type="button" class="cancel-reply">Cancel</button>
        </div>
      `
      const editBtn = document.createElement('button')
      editBtn.innerHTML = '✏️ Edit'
      editBtn.style.background = 'none'
      editBtn.style.border = 'none'
      editBtn.style.cursor = 'pointer'
      editBtn.style.fontSize = '15px'
      editBtn.style.display = 'flex'
      editBtn.style.alignItems = 'center'
      editBtn.style.gap = '4px'

      if (!currentAuthor || getAuthorSerial(entry._author) !== getAuthorSerial(currentAuthor)) {
        editBtn.style.display = 'none'
      }

      const editForm = document.createElement('form')

      let editInput
      switch (entry.contentType) {
        case 'image/png;base64':
        case 'image/jpeg;base64':
        case 'application/base64':
          editInput = document.createElement('input')
          editInput.type = 'file'
          editInput.accept = '.jpeg,.jpg,.png'
          break
        case 'text/plain':
        case 'text/markdown':
          editInput = document.createElement('textarea')
          editInput.value = entry.content
          editInput.style.width = '100%'
          editInput.style.minHeight = '200px'
          editInput.style.whiteSpace = 'pre-wrap'
          editInput.style.overflowWrap = 'break-word'
          break
        default:
          console.error(`Unknown entry content type during entry rendering: ${entry.contentType}`)
      }

      const saveEditBtn = document.createElement('button')
      saveEditBtn.innerHTML = 'Save'

      const deleteEditBtn = document.createElement('button')
      deleteEditBtn.innerHTML = 'Delete'

      const cancelEditBtn = document.createElement('button')
      cancelEditBtn.innerHTML = 'Cancel'

      saveEditBtn.addEventListener('click', (e) => {
        e.preventDefault()

        new Promise((resolve, reject) => {
          switch (entry.contentType) {
            case 'image/png;base64':
            case 'image/jpeg;base64':
            case 'application/base64': {
              const reader = new FileReader()
              const file = editInput.files[0]
              reader.readAsDataURL(file)
              reader.onload = () => {
                const encodedImage = reader.result.split('base64,')[1]
                resolve(encodedImage)
              }
              reader.onerror = reject
              break
            }
            case 'text/plain':
            case 'text/markdown':
              resolve(editInput.value)
              break
            default:
              console.error(`Unknown entry content type during entry rendering: ${entry.contentType}`)
          }
        }).then(content => {
          return fetch(`/api/authors/${getAuthorSerial(entry.author)}/entries/${extractEntryUUID(entry)}/`, {
            method: 'PUT',
            credentials: 'include',
            headers: {
              'X-CSRFToken': getCSRFToken(),
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              title: entry.title,
              description: entry.description,
              contentType: entry.contentType,
              content,
              visibility: entry.visibility
            })
          })
        }).then(res => {
          if (res.ok) {
            console.log('Editted entry.')
            entry.content = editInput.value
            entryContent.innerHTML = ''
            renderEntryContent()
          } else {
            console.log('Could not edit entry.')
          }
        })
      })

      deleteEditBtn.addEventListener('click', (e) => {
        e.preventDefault()

        fetch(`/api/authors/${getAuthorSerial(entry.author)}/entries/${extractEntryUUID(entry)}/`, {
          method: 'DELETE',
          credentials: 'include',
          headers: {
            'X-CSRFToken': getCSRFToken()
          }
        }
        ).then(res => {
          if (res.ok) {
            console.log('Entry deleted.')
            tweet.remove()
          } else {
            console.log('Error deleting entry.')
          }
        })
      })

      cancelEditBtn.addEventListener('click', (e) => {
        e.preventDefault()
        entryContent.innerHTML = ''
        renderEntryContent()
      })

      editForm.appendChild(editInput)
      editForm.appendChild(saveEditBtn)
      editForm.appendChild(deleteEditBtn)
      editForm.appendChild(cancelEditBtn)

      editBtn.addEventListener('click', () => {
        entryContent.innerHTML = ''
        entryContent.appendChild(editForm)
      })

      replyBtn.addEventListener('click', () => {
        replyBox.style.display =
          replyBox.style.display === 'none' ? 'block' : 'none'
        if (replyBox.style.display === 'block') loadReplies(entry, replyList)
      })
      replyForm.querySelector('.cancel-reply').addEventListener('click', (e) => {
        e.preventDefault()
        replyBox.style.display = 'none'
      })
      replyForm.addEventListener('submit', (e) => {
        e.preventDefault()
        const textarea = replyForm.querySelector('textarea')
        const text = textarea.value.trim()
        if (!text) return
        const entryUUID = extractEntryUUID(entry)
        //* **Documentation**
        // ENDPOINT:
        // POST /api/authors/{author_id}/entries/{entry_id}/comments/

        // json:
        // {
        //   "Content-Type": "application/json",
        //   "X-CSRFToken": "<token>"
        // }
        // Purpose: Creates a new comment on the specified entry
        // Response: 201
        // Example:
        // | Field      | Type   | Example Value | Purpose/When to Use               |
        // |------------|--------|--------------|------------------------------------|
        // | author_id  | string | "1234abcd"   | The serial/UUID of the entry author|
        // | entry_id   | string | "5678efgh"   | The UUID of the entry being commented on |
        // | comment    | string | "Nice post!" | The comment text                   |
        fetch(
          `/api/authors/${getAuthorSerial(
            entry._author
          )}/entries/${entryUUID}/comments/`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
              comment: text,
              content: text,
              contentType: 'text/plain'
            }),
            credentials: 'include'
          }
        ).then(() => {
          textarea.value = ''
          loadReplies(entry, replyList)
        })
      })
      replyBox.appendChild(replyList)
      replyBox.appendChild(replyForm)
      const vis = document.createElement('span')
      vis.style.marginLeft = 'auto'
      vis.style.color = '#bbb'
      vis.style.fontSize = '13px'
      vis.textContent = `Visibility: ${entry.visibility}`
      footer.appendChild(likeBtn)
      footer.appendChild(replyBtn)
      footer.appendChild(editBtn)
      footer.appendChild(vis)
      tweet.appendChild(authorRow)
      tweet.appendChild(entryContent)
      tweet.appendChild(footer)
      tweet.appendChild(replyBox)
      tweetList.appendChild(tweet)
    })
  }

  function loadReplies (entry, replyList) {
    replyList.innerHTML = 'Loading…'
    const entryUUID = extractEntryUUID(entry)
    if (!entryUUID) {
      replyList.innerHTML =
        "<span style='color:red'>Entry UUID not found</span>"
      return
    }
    const authorSerial = getAuthorSerial(entry._author)

    fetch(`/api/authors/${authorSerial}/entries/${entryUUID}/comments/`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data || !Array.isArray(data.src) || data.src.length === 0) {
          replyList.innerHTML =
            "<span style='color:#888'>No replies yet. Be the first!</span>"
          return
        }
        replyList.innerHTML = ''
        data.src.forEach((reply) => {
          const replyEl = document.createElement('div')
          replyEl.className = 'reply'
          replyEl.style.padding = '8px'
          replyEl.style.borderTop = '1px solid #eee'

          const replyHeader = document.createElement('div')
          replyHeader.className = 'reply-header'

          const replyAuthorEl = document.createElement('strong')
          replyAuthorEl.textContent = getAuthorName(reply.author)

          const replyTime = document.createElement('span')
          replyTime.style.color = '#777'
          replyTime.style.marginLeft = '8px'
          replyTime.textContent = `• ${timeAgo(reply.published)}`

          replyHeader.appendChild(replyAuthorEl)
          replyHeader.appendChild(replyTime)

          const replyContent = document.createElement('div')
          replyContent.textContent = reply.comment || reply.content || ''

          replyEl.appendChild(replyHeader)
          replyEl.appendChild(replyContent)

          const replyActions = document.createElement('div')
          replyActions.className = 'reply-actions'
          replyActions.style.marginTop = '4px'

          const likeButton = document.createElement('button')
          likeButton.innerHTML = '❤️ Like'
          likeButton.style.background = 'none'
          likeButton.style.border = 'none'
          likeButton.style.cursor = 'pointer'
          likeButton.style.fontSize = '13px'
          likeButton.style.display = 'flex'
          likeButton.style.alignItems = 'center'
          likeButton.style.gap = '4px'
          likeButton.style.padding = '2px 0'

          const commentSerial = reply.serial

          // Fetch likes for this specific comment
          fetch(`/api/authors/${authorSerial}/entries/${entryUUID}/comments/${commentSerial}/likes/`)
            .then(res => res.ok ? res.json() : { src: [] })
            .then(likeData => {
              let likeCount = likeData.src.length
              const liked = likeData.src.some(like => getAuthorSerial(like.author) === getAuthorSerial(currentAuthor))

              if (liked) {
                likeButton.textContent = `❤️ Liked (${likeCount})`
                likeButton.disabled = true
              } else {
                likeButton.textContent = `❤️ Like (${likeCount})`
                likeButton.disabled = false
                likeButton.addEventListener('click', () => {
                  fetch(`/api/authors/${authorSerial}/entries/${entryUUID}/comments/${commentSerial}/likes/`, {
                    method: 'POST',
                    headers: {
                      'X-CSRFToken': getCSRFToken(),
                      'Content-Type': 'application/json'
                    },
                    credentials: 'include'
                  })
                    .then(res => {
                      if (res.status === 201) {
                        likeCount++
                        likeButton.textContent = `❤️ Liked (${likeCount})`
                        likeButton.disabled = true
                      } else {
                        alert('Failed to like the comment.')
                      }
                    })
                    .catch(err => console.error('Error liking comment:', err))
                }, { once: true })
              }
            })

          replyActions.appendChild(likeButton)
          replyEl.appendChild(replyActions)

          replyList.appendChild(replyEl)
        })
      })
      .catch(() => {
        replyList.innerHTML =
          "<span style='color:red'>Failed to load replies.</span>"
      })
  }

  function loadFriendRequests (currentAuthor) {
    const listContainer = document.querySelector('.friend-requests-list')
    if (!listContainer || !currentAuthor) return

    const mySerial = getAuthorSerial(currentAuthor)
    listContainer.innerHTML =
      '<div style="color:#999; font-size:14px;">Loading requests...</div>'

    fetch(`/api/authors/${mySerial}/follow-requests/`, {
      credentials: 'include'
    })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load requests')
        return res.json()
      })
      .then((requests) => {
        listContainer.innerHTML = ''
        if (!requests || requests.length === 0) {
          listContainer.innerHTML =
            '<div style="color:#999; font-size:14px;">No pending requests.</div>'
          return
        }

        requests.forEach((req) => {
          const requester = req.actor
          const requesterSerial = getAuthorSerial(requester)

          const reqDiv = document.createElement('div')
          reqDiv.className = 'friend-request-item'
          reqDiv.style.display = 'flex'
          reqDiv.style.alignItems = 'center'
          reqDiv.style.justifyContent = 'space-between'
          reqDiv.style.padding = '8px 0'
          reqDiv.style.borderBottom = '1px solid #f0f0f0'

          // Author info container (name, node, profile link)
          const authorInfoDiv = document.createElement('div')
          authorInfoDiv.style.display = 'flex'
          authorInfoDiv.style.flexDirection = 'column'
          authorInfoDiv.style.gap = '4px'
          authorInfoDiv.style.flex = '1'

          // Main author name with profile link
          const authorLink = document.createElement('a')
          authorLink.textContent = getAuthorName(requester)
          authorLink.style.fontWeight = '500'
          authorLink.style.textDecoration = 'none'
          authorLink.style.color = '#1da1f2'
          authorLink.style.cursor = 'pointer'

          // Link to author profile
          if (requester.web) {
            authorLink.href = requester.web
          } else {
            if (requesterSerial) {
              authorLink.href = `/authors/${requesterSerial}/`
            }
          }

          // Node information
          const nodeInfo = document.createElement('div')
          nodeInfo.style.fontSize = '12px'
          nodeInfo.style.color = '#666'

          // Extract node name from host
          let nodeName = 'Local'
          if (requester.host) {
            try {
              const hostUrl = new URL(requester.host)
              nodeName = hostUrl.hostname
            } catch (e) {
              nodeName = requester.host
            }
          }

          // Show node and serial info
          const serialShort = requesterSerial ? requesterSerial.substring(0, 8) + '...' : 'unknown'
          nodeInfo.textContent = `@${serialShort} • ${nodeName}`

          authorInfoDiv.appendChild(authorLink)
          authorInfoDiv.appendChild(nodeInfo)

          const buttonsDiv = document.createElement('div')
          buttonsDiv.style.display = 'flex'
          buttonsDiv.style.gap = '6px'

          const acceptBtn = document.createElement('button')
          acceptBtn.textContent = 'Accept'
          acceptBtn.className = 'accept-btn'
          acceptBtn.onclick = () => {
            // UPDATE THIS FETCH CALL
            fetch(`/api/authors/${mySerial}/followers/${requesterSerial}/`, {
              method: 'PUT',
              credentials: 'include',
              headers: {
                'X-CSRFToken': getCSRFToken()
              }
            }).then((res) => {
              if (res.ok) {
                reqDiv.remove()
              } else {
                alert('Failed to accept request.')
              }
            })
          }

          const denyBtn = document.createElement('button')
          denyBtn.textContent = 'Deny'
          denyBtn.className = 'deny-btn'
          denyBtn.onclick = () => {
            // UPDATE THIS FETCH CALL
            fetch(`/api/authors/${mySerial}/followers/${requesterSerial}/`, {
              method: 'DELETE',
              credentials: 'include',
              headers: {
                'X-CSRFToken': getCSRFToken()
              }
            }).then((res) => {
              if (res.ok) {
                reqDiv.remove()
              } else {
                alert('Failed to deny request.')
              }
            })
          }

          buttonsDiv.appendChild(acceptBtn)
          buttonsDiv.appendChild(denyBtn)
          reqDiv.appendChild(authorInfoDiv)
          reqDiv.appendChild(buttonsDiv)
          listContainer.appendChild(reqDiv)
        })
      })
      .catch((err) => {
        console.error('Error loading friend requests:', err)
        listContainer.innerHTML =
          '<div style="color:red; font-size:14px;">Could not load requests.</div>'
      })
  }

  // --- Search Functionality ---
  function initializeSearch () {
    const searchInput = document.getElementById('search-input')
    const searchResultsList = document.getElementById('search-results-list')
    let debounceTimer

    searchInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer)
      const searchTerm = e.target.value.trim()

      debounceTimer = setTimeout(() => {
        if (searchTerm.length > 0) {
          performSearch(searchTerm)
        } else {
          searchResultsList.innerHTML = '' // Clear results if input is empty
        }
      }, 300) // 300ms debounce
    })

    function performSearch (term) {
      fetch(`/api/authors/?search=${encodeURIComponent(term)}`)
        .then((res) => res.json())
        .then((data) => {
          renderSearchResults(data.authors || [])
        })
        .catch((error) => {
          console.error('Search failed:', error)
          searchResultsList.innerHTML =
            '<div class="error">Search failed to load.</div>'
        })
    }

    function renderSearchResults (authors) {
      searchResultsList.innerHTML = ''
      if (!authors.length) {
        searchResultsList.innerHTML = '<div>No authors found.</div>'
        return
      }

      authors.forEach((author) => {
        const itemDiv = document.createElement('div')
        itemDiv.className = 'search-result-item'

        // Author info container (name, node, profile link)
        const authorInfoDiv = document.createElement('div')
        authorInfoDiv.className = 'search-result-author-info'
        authorInfoDiv.style.display = 'flex'
        authorInfoDiv.style.flexDirection = 'column'
        authorInfoDiv.style.gap = '4px'
        authorInfoDiv.style.flex = '1'

        // Main author name with profile link
        const authorLink = document.createElement('a')
        authorLink.className = 'search-result-name-link'
        authorLink.textContent = getAuthorName(author)
        authorLink.style.fontWeight = '500'
        authorLink.style.textDecoration = 'none'
        authorLink.style.color = '#1da1f2'
        authorLink.style.cursor = 'pointer'

        // Link to author profile
        if (author.web) {
          authorLink.href = author.web
        } else {
          const authorSerial = getAuthorSerial(author)
          if (authorSerial) {
            authorLink.href = `/authors/${authorSerial}/`
          }
        }

        // Node information
        const nodeInfo = document.createElement('div')
        nodeInfo.className = 'search-result-node-info'
        nodeInfo.style.fontSize = '12px'
        nodeInfo.style.color = '#666'

        // Extract node name from host
        let nodeName = 'Local'
        if (author.host) {
          try {
            const hostUrl = new URL(author.host)
            nodeName = hostUrl.hostname
          } catch (e) {
            nodeName = author.host
          }
        }

        // Show node and serial info
        const authorSerial = getAuthorSerial(author)
        const serialShort = authorSerial ? authorSerial.substring(0, 8) + '...' : 'unknown'
        nodeInfo.textContent = `@${serialShort} • ${nodeName}`

        authorInfoDiv.appendChild(authorLink)
        authorInfoDiv.appendChild(nodeInfo)

        const followBtn = document.createElement('button')
        followBtn.textContent = 'Follow'
        followBtn.className = 'follow-btn'
        followBtn.style.flexShrink = '0'
        followBtn.onclick = () => handleFollow(author, followBtn)

        itemDiv.style.display = 'flex'
        itemDiv.style.alignItems = 'center'
        itemDiv.style.gap = '12px'
        itemDiv.style.padding = '8px 0'
        itemDiv.style.borderBottom = '1px solid #f0f0f0'

        itemDiv.appendChild(authorInfoDiv)
        itemDiv.appendChild(followBtn)
        searchResultsList.appendChild(itemDiv)
      })
    }

    function handleFollow (targetAuthor, button) {
      if (!currentAuthor) {
        alert('Cannot follow: current user not identified.')
        return
      }

      button.disabled = true
      button.textContent = 'Sending...'

      const targetSerial = getAuthorSerial(targetAuthor)
      if (!targetSerial) {
        alert('Target author is invalid.')
        button.disabled = false
        button.textContent = 'Follow'
        return
      }

      // Check if this is a remote author
      const isRemoteAuthor = isAuthorRemote(targetAuthor)

      // The inbox expects a full follow request object
      const followRequestPayload = {
        type: 'follow',
        summary: `${getAuthorName(currentAuthor)} wants to follow ${getAuthorName(
          targetAuthor
        )}`,
        actor: currentAuthor, // The full author object is sufficient
        object: targetAuthor // The full author object is sufficient
      }

      fetch(`/api/authors/${targetSerial}/inbox/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify(followRequestPayload),
        credentials: 'include'
      })
        .then((res) => {
          if (res.status === 201 || res.status === 200) {
            // Success - follow request sent or already exists
            if (isRemoteAuthor) {
              button.textContent = 'Following (Remote)'
            } else {
              button.textContent = 'Requested'
            }
            // The button remains disabled
          } else {
            return res.json().then((err) => Promise.reject(err))
          }
        })
        .catch((error) => {
          console.error('Follow request failed:', error)
          const errorMsg = error.detail || error.message || 'Unknown error'
          alert(`Failed to send follow request: ${errorMsg}`)
          button.disabled = false
          button.textContent = 'Follow'
        })
    }

    // Helper function to determine if an author is remote
    function isAuthorRemote (author) {
      if (!author || !author.host) return false

      // Get current host
      const currentHost = window.location.protocol + '//' + window.location.host + '/'
      const authorHost = author.host.endsWith('/') ? author.host : author.host + '/'

      return authorHost !== currentHost
    }
  }

  // --- Helper Functions ---
  function getAuthorName (authorObj) {
    if (!authorObj) return '(unknown)'
    if (authorObj.displayName) return authorObj.displayName
    if (authorObj.username) return authorObj.username
    if (typeof authorObj === 'string') return authorObj.split('/').pop()
    return '(unknown)'
  }

  function getAuthorSerial (authorObj) {
    if (!authorObj || !authorObj.id) return ''
    const parts = authorObj.id.split('/').filter(Boolean)
    return parts.pop()
  }

  function extractEntryUUID (entry) {
    if (entry.serial) return entry.serial
    if (!entry.id) return undefined
    const parts = entry.id.split('/')
    const idx = parts.findIndex((part) => part === 'entries')
    return idx !== -1 && parts[idx + 1] ? parts[idx + 1] : undefined
  }

  function timeAgo (date) {
    if (!date) return ''
    const d = new Date(date)
    const now = new Date()
    const diff = Math.floor((now - d) / 1000)
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return d.toLocaleDateString()
  }

  // --- Start the application ---
  initializeSearch()
  loadGlobalFeed()
})
