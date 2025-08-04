import { generateCommonmarkHtml } from '../../../../../../static/renderer.min.js'

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

// Process markdown content for entries on page load
document.addEventListener('DOMContentLoaded', () => {
  const tweetList = document.querySelector('.tweet-list')
  const currentUserSerial = window.currentAuthor.serial

  const pathParts = window.location.pathname.split('/')
  const authorSerial = pathParts[2]

  const profilePic = document.getElementById('profile-pic-bio')
  const profileID = document.getElementById('profile-id-bio')
  const nameContainer = document.getElementById('profile-name-container')
  const headerContainer = document.getElementById('profile-header-container')

  const displayNameInput = document.getElementById('display-name')
  const githubInput = document.getElementById('github-url')
  const profileImageUpload = document.getElementById('profile-image-upload')
  const form = document.getElementById('author-edit-form')
  const statusMsg = document.getElementById('update-status')
  const modal = document.getElementById('edit-modal-container')
  const penIcon = document.getElementById('edit-link')
  const closeBtn = document.getElementById('close-modal')

  penIcon.addEventListener('click', () => {
    modal.style.display = 'flex'
  })

  closeBtn.addEventListener('click', () => {
    modal.style.display = 'none'
  })

  window.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.style.display = 'none'
    }
  })

  if (penIcon) {
    if (authorSerial === currentUserSerial) {
      penIcon.style.display = 'block'
    } else {
      penIcon.style.display = 'none'
    }
  }

  form.addEventListener('submit', async e => {
    e.preventDefault()

    const csrftoken = getCSRFToken()
    statusMsg.textContent = 'Updating...'
    statusMsg.style.color = 'orange'

    try {
      let newImageUrl = null
      const file = profileImageUpload.files[0]

      if (file) {
        // 1. If an image is uploaded, create a new entry for it
        const content = await toBase64(file)
        const contentType = file.type === 'image/png' ? 'image/png;base64' : 'image/jpeg;base64'

        const entryRes = await fetch(`/api/authors/${authorSerial}/entries/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Csrftoken': csrftoken
          },
          body: JSON.stringify({
            title: 'New Profile Picture',
            description: 'A new profile picture was uploaded.',
            contentType,
            content,
            visibility: 'PUBLIC'
          }),
          credentials: 'include'
        })

        if (!entryRes.ok) {
          const errorData = await entryRes.json()
          throw new Error(`Failed to create image entry: ${JSON.stringify(errorData)}`)
        }

        const newEntry = await entryRes.json()
        const newImageUrlPath = new URL(newEntry.id, window.location.origin).pathname
        newImageUrl = `${window.location.origin}${newImageUrlPath}/image`
      }

      // 2. Update author profile with other fields and new image URL if available
      const updatedAuthor = {}
      const displayNameVal = displayNameInput.value.trim()
      if (displayNameVal) {
        updatedAuthor.displayName = displayNameVal
      }

      const githubVal = githubInput.value.trim()
      if (githubVal) {
        updatedAuthor.github = githubVal
      }

      if (newImageUrl) {
        updatedAuthor.profileImage = newImageUrl
      }

      if (Object.keys(updatedAuthor).length > 0) {
        const authorUpdateRes = await fetch(`/api/authors/${authorSerial}/`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'X-Csrftoken': csrftoken
          },
          body: JSON.stringify(updatedAuthor),
          credentials: 'include'
        })

        if (!authorUpdateRes.ok) {
          const errorData = await authorUpdateRes.json()
          throw new Error(`Failed to update profile: ${JSON.stringify(errorData)}`)
        }

        const updatedAuthorData = await authorUpdateRes.json()
        // Update UI with new data and error handling
        if (updatedAuthorData.profileImage) {
          profilePic.src = updatedAuthorData.profileImage
          profilePic.onerror = function () {
            this.src = '/static/images/defaultprofile.webp'
          }
        } else {
          profilePic.src = '/static/images/defaultprofile.webp'
        }
      }

      statusMsg.textContent = 'Profile updated successfully!'
      statusMsg.style.color = 'green'
    } catch (error) {
      console.error(error)
      statusMsg.textContent = error.message
      statusMsg.style.color = 'red'
    }
  })
  const toBase64 = file => new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.readAsDataURL(file)
    reader.onload = () => {
      let encoded = reader.result.toString().replace(/^data:(.*,)?/, '')
      if ((encoded.length % 4) > 0) {
        encoded += '='.repeat(4 - (encoded.length % 4))
      }
      resolve(encoded)
    }
    reader.onerror = error => reject(error)
  })

  fetch(`/api/authors/${authorSerial}/`)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`)
      return res.json()
    })
    .then((author) => {
      if (!author) return

      profileID.textContent = `@${getAuthorSerial(author)}`

      document.getElementById('following-count').textContent = author.following_count ?? 0
      document.getElementById('followers-count').textContent = author.followers_count ?? 0
      document.getElementById('friends-count').textContent =
        author.friends_count ?? 0
      document.getElementById('following-link').href = `/authors/${authorSerial}/following/`
      document.getElementById('followers-link').href = `/authors/${authorSerial}/followers/`
      document.getElementById(
        'friends-link'
      ).href = `/authors/${authorSerial}/friends/`
      nameContainer.textContent = author.displayName || 'Unnamed User'

      // Update profile image with error handling
      if (author.profileImage) {
        profilePic.src = author.profileImage
        profilePic.onerror = function () {
          this.src = '/static/images/defaultprofile.webp'
        }
      } else {
        profilePic.src = '/static/images/defaultprofile.webp'
      }

      if (author.github) {
        let ghLink = author.github
        if (!ghLink.startsWith('http')) ghLink = 'https://github.com/' + ghLink
        const githubLinkElement = document.querySelector('.github-link')
        githubLinkElement.href = ghLink
        // Extract just the username for the link text
        githubLinkElement.childNodes[2].nodeValue = ' ' + author.github.split('/').pop()
      } else {
        const githubLinkElement = document.querySelector('.github-link')
        if (githubLinkElement) {
          githubLinkElement.style.display = 'none' // Hides the link
        }
      }

      // Append friend badge if is_friend true
      if (author.is_friend) {
        const friendBadge = document.createElement('span')
        friendBadge.className = 'friend-badge'
        friendBadge.textContent = 'Friends'
        nameContainer.appendChild(friendBadge)
      }
    })
    .catch((err) => {
      headerContainer.innerHTML = '<p style="color: red;">Failed to load profile.</p>'
      console.error(err)
    })

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

  function loadAuthorFeed () {
    // Authenticated user flow
    fetchAllAuthors()
      .then((authors) => {
        if (!authors.length) {
          tweetList.innerHTML =
            '<div style="color:#999;">No author found on this server.</div>'
          return
        }
        const currentAuthor = authors.find((author) => {
          const authorSerial = getAuthorSerial(author)
          return authorSerial === currentUserSerial
        })
        if (!currentAuthor) {
          console.error('Could not find current user in author list.')
          return
        }
        updateProfileUI(currentAuthor)
        loadMenu(currentAuthor)
        renderEntries(currentAuthor)
      })
      .catch((error) => {
        console.error('Failed to fetch authors:', error)
        tweetList.innerHTML =
          '<div style="color:red;">Error loading authors.</div>'
      })
  }
  function loadMenu (currentAuthor) {
    const homeButton = document.getElementById('home-menu-button')
    const profileButton = document.getElementById('profile-menu-button')
    const connectButton = document.getElementById('connect-menu-button')
    const postMenuButton = document.getElementById('post-menu-button')

    homeButton.addEventListener('click', () => {
      window.location.href = '/'
    })

    profileButton.addEventListener('click', () => {
      window.location.href = `/authors/${currentUserSerial}/`
    })

    connectButton.addEventListener('click', () => {
      window.location.href = '/connect/'
    })

    if (authorSerial !== currentUserSerial) {
      connectButton.style.backgroundColor = '#f2f2f2ff'
      connectButton.style.borderRight = '3px solid #0cc0df'
    } else {
      profileButton.style.borderRight = '3px solid #0cc0df'
      profileButton.style.backgroundColor = '#f2f2f2ff'
    }

    postMenuButton.addEventListener('click', () => {
      window.location.href = '/?openModal=true'
    })
  }

  function updateProfileUI (author) {
    if (!author) return

    const authorSerial = getAuthorSerial(author)

    // find existing profile-name element
    let nameEl = document.querySelector(
      '.profile-section .profile-name'
    )

    // if it doesn’t exist or isn’t a div, recreate it
    if (!nameEl || nameEl.tagName.toLowerCase() !== 'p') {
      if (nameEl) nameEl.remove()

      nameEl = document.createElement('p')
      nameEl.className = 'profile-name'
      nameEl.style.fontWeight = 'bold'
      nameEl.style.marginTop = '10px'

      document
        .querySelector('.profile-section')
        .insertBefore(nameEl, document.querySelector('.profile-info'))
    }

    nameEl.textContent = author.displayName
    nameEl.addEventListener('click', () => {
      window.location.href = `/authors/${authorSerial}/`
    })
    nameEl.style.cursor = 'pointer'

    let userID = document.querySelector(
      '.profile-section .profile-id'
    )

    // if it doesn’t exist or isn’t a div, recreate it
    if (!userID || userID.tagName.toLowerCase() !== 'p') {
      if (userID) userID.remove()

      userID = document.createElement('p')
      userID.className = 'profile-id'
      userID.style.fontWeight = 'bold'
      userID.style.marginTop = '10px'

      document
        .querySelector('.profile-section')
        .insertBefore(userID, document.querySelector('.profile-info'))
    }

    userID.textContent = `@${getAuthorSerial(author)}`

    const profilePicElement = document.querySelector('.profile-pic')
    if (author.profileImage) {
      profilePicElement.src = author.profileImage
      profilePicElement.onerror = function () {
        this.src = '/static/images/defaultprofile.webp'
      }
    } else {
      profilePicElement.src = '/static/images/defaultprofile.webp'
    }

    profilePicElement.addEventListener('click', () => {
      window.location.href = `/authors/${authorSerial}/`
    })
    profilePicElement.style.cursor = 'pointer'
  }

  function renderEntries (currentAuthor) {
    const entries = window.entries
    const emptyFeedMessage = document.getElementById('empty-feed-message')

    if (!entries || entries.length === 0) {
      emptyFeedMessage.style.display = 'block'
    } else {
      emptyFeedMessage.style.display = 'none'
    }

    tweetList.innerHTML = ''
    entries.forEach((entry) => {
      console.log(entry)
      const tweet = document.createElement('article')
      tweet.className = 'tweet'
      const webUrl = entry.author.web
      const authorPicLink = document.createElement('a')
      authorPicLink.href = webUrl
      authorPicLink.style.display = 'inline-block'
      const authorPic = document.createElement('img')
      authorPic.className = 'profile-pic'
      authorPic.style.width = '36px'
      authorPic.style.height = '36px'
      authorPic.alt = 'User Pic'
      if (entry.author.profileImage) {
        authorPic.src = entry.author.profileImage
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
      strong.textContent = getAuthorName(entry.author)
      authorNameLink.appendChild(strong)
      const uuidSpan = document.createElement('span')
      uuidSpan.style.fontSize = '13px'
      uuidSpan.style.color = '#aaa'
      uuidSpan.textContent = `@${getAuthorSerial(entry.author).substring(
        0,
        8
      )}... • ${timeAgo(entry.published)}`

      const authorRow = document.createElement('div')
      authorRow.className = 'tweet-header'
      authorRow.style.display = 'flex'
      authorRow.style.alignItems = 'center'
      authorRow.style.gap = '10px'
      authorRow.appendChild(authorPicLink)
      authorRow.appendChild(authorNameLink)
      authorRow.appendChild(uuidSpan)

      const postMenuButton = document.createElement('button')
      postMenuButton.textContent = '...'
      postMenuButton.className = 'post-menu-button'

      const postModal = document.createElement('div')
      postModal.className = 'post-modal'

      const backdrop = document.createElement('div')
      backdrop.className = 'post-modal-backdrop'

      const postModalContainer = document.createElement('div')
      postModalContainer.className = 'post-modal-container'

      const option1 = document.createElement('a')
      option1.href = '#'
      option1.textContent = 'Edit Post'
      postModalContainer.appendChild(option1)
      if (!currentAuthor || getAuthorSerial(entry.author) !== getAuthorSerial(currentAuthor)) {
        option1.style.display = 'none'
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

      option1.addEventListener('click', () => {
        entryContent.innerHTML = ''
        entryContent.appendChild(editForm)
        postModal.style.display = 'none'
        backdrop.style.display = 'none'
      })

      const option2 = document.createElement('a')
      option2.textContent = 'Copy Post Link'
      postModalContainer.appendChild(option2)
      option2.addEventListener('click', function (e) {
        navigator.clipboard.writeText(fqidToLocalEntryUrl(entry.id))
          .then(() => {
            alert('Link copied to clipboard!')
          })
          .catch(err => {
            console.error('Error copying the text: ', err)
          })
      })

      const option3 = document.createElement('a')
      option3.href = fqidToLocalEntryUrl(entry.id)
      option3.textContent = 'Open Post In New Tab'
      option3.target = '_blank'
      postModalContainer.appendChild(option3)

      postModal.appendChild(postModalContainer)

      tweet.appendChild(backdrop)
      tweet.appendChild(postModal)

      postMenuButton.addEventListener('click', function () {
        postModal.style.display = 'block'
        backdrop.style.display = 'block'
      })

      backdrop.addEventListener('click', function () {
        postModal.style.display = 'none'
        backdrop.style.display = 'none'
      })
      window.addEventListener('click', (e) => {
        if (!postModal.contains(e.target) && e.target !== postMenuButton) {
          postModal.style.display = 'none'
          backdrop.style.display = 'none'
        }
      })

      authorRow.appendChild(postMenuButton)

      const entryContent = document.createElement('div')
      entryContent.className = 'tweet-content'

      function renderEntryContent () {
        entryContent.style.margin = '10px 0 6px 0'
        if (entry.title) {
          const title = document.createElement('h2')
          title.style.fontWeight = '600'
          title.textContent = entry.title
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
              entryImage.src = '/static/images/defaultphoto.jpg'
              // this.style.display = 'none'
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
      footer.className = 'tweet-footer'
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
      const authorSerial = getAuthorSerial(entry.author)

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
            entry.author
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
      footer.appendChild(vis)
      tweet.appendChild(authorRow)
      tweet.appendChild(entryContent)
      tweet.appendChild(footer)
      tweet.appendChild(replyBox)
      tweetList.appendChild(tweet)
    })
  }

  function loadReplies (entry, replyList, currentAuthor) {
    replyList.innerHTML = 'Loading…'
    const entryUUID = extractEntryUUID(entry)
    if (!entryUUID) {
      replyList.innerHTML =
        "<span style='color:red'>Entry UUID not found</span>"
      return
    }
    const authorSerial = getAuthorSerial(entry.author)

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
  loadAuthorFeed()
})
