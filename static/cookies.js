window.getCookie = function (cookieName) {
  let cookieValue = null
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';')
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim()
      if (cookie.substring(0, cookieName.length + 1) === (cookieName + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(cookieName.length + 1))
        break
      }
    }
  }
  return cookieValue
}
