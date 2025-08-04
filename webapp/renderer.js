import { Parser, HtmlRenderer } from 'commonmark'
import DOMPurify from 'dompurify'

// Checks if a URL is local or a data URI to prevent requests to external servers.
function isUrlLocal (url) {
  // Data URIs are self-contained and always considered local.
  if (url.startsWith('data:')) {
    return true
  }

  try {
    // Resolve the URL against the current page's location. If the origin
    // matches the document's origin, the URL is local.
    const absoluteUrl = new URL(url, window.location.href)
    if (absoluteUrl.origin === window.location.origin) {
      return true
    }

    // Allow all external images for markdown content
    return true
  } catch (e) {
    // Malformed URLs are not considered local.
    return false
  }
}

export function generateCommonmarkHtml (markdownText) {
  // Sanitize input
  const sanitizedMarkdown = DOMPurify.sanitize(markdownText)

  const reader = new Parser()
  const writer = new HtmlRenderer({ safe: true })

  const parsed = reader.parse(sanitizedMarkdown)
  const walker = parsed.walker()
  let event

  // Find and process image nodes before rendering.
  while ((event = walker.next())) {
    const node = event.node
    if (event.entering && node.type === 'image') {
      if (!isUrlLocal(node.destination)) {
        // Block external images by replacing their URL.
        const originalUrl = node.destination
        node.destination = '#'
        node.title = `External image from ${originalUrl} was blocked for security.`
      }
    }
  }
  // Render the safe document tree to HTML.
  return writer.render(parsed)
}
