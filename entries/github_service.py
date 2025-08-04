import requests
import json
from datetime import datetime
from .models import Entry
from authors.models import Author
# gnerated by Genimi 2.5pro 2025-07-07


def _format_push_event(event: dict) -> dict:
    """Formats a PushEvent into Entry fields."""
    repo_name = event['repo']['name']
    commit_count = len(event['payload']['commits'])
    plural_s = 's' if commit_count > 1 else ''
    title = f"Pushed {commit_count} commit{plural_s} to {repo_name}"
    description = event['payload']['commits'][0]['message']
    content_lines = [f"### Commits pushed to `{repo_name}`:"]
    for commit in event['payload']['commits']:
        commit_sha = commit['sha'][:7]
        commit_url = commit['url'].replace(
            "api.github.com/repos", "github.com")
        message = commit['message']
        content_lines.append(f"- [`{commit_sha}`]({commit_url}): {message}")
    return {
        "title": title,
        "description": description,
        "content": "\n".join(content_lines)}


def _format_create_event(event: dict) -> dict:
    """Formats a CreateEvent into Entry fields."""
    repo_name = event['repo']['name']
    repo_url = f"https://github.com/{repo_name}"
    title = f"Created a new repository: {repo_name}"
    description = event['payload'].get(
        'description') or "A new project was started."
    content = f"I just created a new public repository named " \
        f"**[{repo_name}]({repo_url})**."
    return {"title": title, "description": description, "content": content}


def _format_watch_event(event: dict) -> dict:
    """Formats a WatchEvent (starring a repo) into Entry fields."""
    repo_name = event['repo']['name']
    repo_url = f"https://github.com/{repo_name}"
    title = f"Starred a repository: {repo_name}"
    description = f"I'm now following the {repo_name} repository."
    content = f"I starred the repository " \
        f"**[{repo_name}]({repo_url})** to follow its progress."
    return {"title": title, "description": description, "content": content}


def process_github_events(author: Author):
    """
    Fetches public GitHub events for an author and creates new Entry objects
    for any events that haven't been imported yet.
    """
    if not author.is_authenticated or not author.github:
        return

    try:
        username = author.github.strip('/').split('/')[-1]
        if not username:
            return
    except (IndexError, AttributeError):
        return

    api_url = f"https://api.github.com/users/{username}/events/public"

    try:
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        events = response.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        # Fail silently if the API call doesn't work
        return

    if not events:
        return

    EVENT_HANDLERS = {
        'PushEvent': _format_push_event,
        'CreateEvent': _format_create_event,
        'WatchEvent': _format_watch_event,
    }

    new_entries_created = 0
    for event in reversed(events):
        event_id = event['id']
        event_type = event['type']

        if Entry.objects.filter(github_event_id=event_id).exists():
            continue

        if event_type not in EVENT_HANDLERS:
            continue

        handler = EVENT_HANDLERS[event_type]
        entry_data = handler(event)

        try:
            published_time = datetime.fromisoformat(
                event['created_at'].replace('Z', '+00:00'))

            Entry.objects.create(
                author=author,
                github_event_id=event_id,
                title=entry_data['title'],
                description=entry_data['description'],
                content=entry_data['content'],
                content_type='text/markdown',
                visibility='PUBLIC',
                published=published_time,
            )
            new_entries_created += 1
        except Exception:
            # If creating the entry fails for any reason, skip it
            continue

    if new_entries_created > 0:
        print(
            f"Created {new_entries_created} new entries from GitHub "
            f"events for author '{author.display_name}'.")
