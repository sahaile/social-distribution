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

document.addEventListener('DOMContentLoaded', () => {
  const authorList = document.querySelector('.author-list')
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

  function loadGlobalFeed () {
    const currentUserSerial = window.currentUserSerial

    // Authenticated user flow
    fetchAllAuthors()
      .then((authors) => {
        if (!authors.length) {
          authorList.textContent =
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
        loadMenu(currentAuthor)
        loadAuthors(currentAuthor, authors)
      })
      .catch((error) => {
        console.error('Failed to fetch authors:', error)
        authorList.innerHTML =
          '<div style="color:red;">Error loading authors.</div>'
      })
  }

  function loadMenu (currentAuthor) {
    const homeButton = document.getElementById('home-menu-button')
    homeButton.addEventListener('click', () => {
      window.location.href = '/'
    })

    const profileButton = document.getElementById('profile-menu-button')
    profileButton.addEventListener('click', () => {
      window.location.href = `/authors/${getAuthorSerial(currentAuthor)}/`
    })

    const connectButton = document.getElementById('connect-menu-button')
    connectButton.addEventListener('click', () => {
      // Adjust the URL for the Connect page or wherever you want to redirect
      window.location.href = '/connect/'
    })
    connectButton.style.borderRight = '3px solid #0cc0df'
    connectButton.style.backgroundColor = '#f2f2f2ff'

    const postMenuButton = document.getElementById('post-menu-button')

    postMenuButton.addEventListener('click', () => {
      window.location.href = '/?openModal=true'
    })
  }

  function loadAuthors (currentAuthor, authors) {
    const authorList = document.querySelector('.author-list')
    authorList.innerHTML = ''

    if (!currentAuthor) {
      authorList.innerHTML = '<p>No current author logged in.</p>'
      return
    }

    const currentAuthorSerial = getAuthorSerial(currentAuthor)

    fetch(`/api/authors/${currentAuthorSerial}/following/`, { credentials: 'include' })
      .then(res => {
        if (!res.ok) throw new Error('Failed to load following list')
        return res.json()
      })
      .then(data => {
        const following = data.following || []

        // Build a Set of serials for quick lookup
        const followingSerials = new Set(
          following.map(user => {
            const parts = user.id.split('/').filter(Boolean)
            return parts[parts.length - 1]
          })
        )

        const filteredAuthors = authors.filter(author =>
          getAuthorSerial(author) !== currentAuthorSerial &&
        author.displayName
        )

        if (filteredAuthors.length === 0) {
          authorList.innerHTML = '<p>No other authors found.</p>'
          return
        }

        filteredAuthors.forEach(author => {
          const authorSerial = getAuthorSerial(author)

          const authorDiv = document.createElement('div')
          authorDiv.classList.add('author-item')
          authorDiv.style.display = 'flex'
          authorDiv.style.alignItems = 'center'
          authorDiv.style.padding = '8px 0'
          authorDiv.style.borderBottom = '1px solid #f0f0f0'

          const authorPic = document.createElement('img')
          authorPic.className = 'profile-pic'
          authorPic.style.width = '80px'
          authorPic.style.height = '80px'
          authorPic.alt = 'User Pic'
          if (author.profileImage) {
            authorPic.src = author.profileImage
            authorPic.onerror = function () {
              this.src = '/static/images/defaultprofile.webp'
            }
          } else {
            authorPic.src = '/static/images/defaultprofile.webp'
          }
          authorDiv.appendChild(authorPic)

          authorDiv.addEventListener('click', () => {
            window.location.href = `/authors/${authorSerial}/`
          })

          // Author name
          const nameEl = document.createElement('p')
          nameEl.textContent = author.displayName || author.username || 'Unknown Author'
          nameEl.style.margin = '0'
          nameEl.style.fontSize = '18px'
          authorDiv.appendChild(nameEl)

          // Author serial (id)
          const userID = document.createElement('p')
          userID.textContent = `@${authorSerial}`
          userID.style.margin = '0'
          userID.style.fontSize = '12px'
          userID.style.color = '#818181'
          userID.style.width = '70%'
          authorDiv.appendChild(userID)

          // Decide if follow button should show
          if (!followingSerials.has(authorSerial)) {
            const followBtn = document.createElement('button')
            followBtn.textContent = 'Follow'
            followBtn.className = 'follow-btn'
            followBtn.style.marginTop = '8px'
            followBtn.addEventListener('click', (event) => {
              event.stopPropagation()
              handleFollow(author, followBtn)
            })
            authorDiv.appendChild(followBtn)
          }
          authorList.appendChild(authorDiv)
        })
      })
      .catch(err => {
        console.error('Error loading following list:', err)
        authorList.innerHTML = '<p style="color:red;">Failed to load authors properly.</p>'
      })
  }

  function updateProfileUI (author) {
    if (!author) return
    const authorSerial = getAuthorSerial(author)

    const profileSection = document.querySelector('.profile-section')
    profileSection.addEventListener('click', () => {
      window.location.href = `/authors/${authorSerial}/`
    })

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

    fetchDefaultAuthors()

    searchInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer)
      const searchTerm = e.target.value.trim()

      debounceTimer = setTimeout(() => {
        if (searchTerm.length > 0) {
          performSearch(searchTerm)
        } else {
          searchResultsList.innerHTML = '' // Clear results if input is empty
          fetchDefaultAuthors()
        }
      }, 300) // 300ms debounce
    })

    function fetchDefaultAuthors () {
      fetchAllAuthors().then((authors) => {
        const currentAuthorSerial = getAuthorSerial(currentAuthor)
        const filteredAuthors = authors.filter(author =>
          getAuthorSerial(author) !== currentAuthorSerial &&
                author.displayName
        )
        if (filteredAuthors.length === 0) {
          authorList.innerHTML = '<p>No other authors found.</p>'
          return
        }

        const count = Math.min(filteredAuthors.length, 5)
        const defaultAuthors = filteredAuthors.slice(0, count)
        renderSearchResults(defaultAuthors)
      }).catch(error => {
        console.error('Failed to load authors:', error)
      })
    }

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
        authorLink.style.color = '#0cc0df'
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

  // --- Start the application ---
  loadGlobalFeed()
  initializeSearch()
})
