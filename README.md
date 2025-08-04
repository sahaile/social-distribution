SocialDistribution
===================================

CMPUT 404 Spring/Summer 2025 Project

See [the web page](https://uofa-cmput404.github.io/general/project.html) for a description of the project.

Make a distributed social network!

## Team Members
| CCID     | Github Username                                         |
|----------|---------------------------------------------------------|
| ziqi24   | [ziqizhang42](https://github.com/ziqizhang42)           |
| lyunze   | [Davidsharkdododo](https://github.com/Davidsharkdododo) |
| sahaile  | [sahaile](https://github.com/sahaile)                   |
| jns      | [Nosajsom](https://github.com/Nosajsom)                 |
| shaian   | [ShaianSh](https://github.com/ShaianSh)                 |
| zejia    | [Jameszf](https://github.com/Jameszf)                   |

## License

All files in this repository are licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Dependencies

* Python 3.13.3 (see requirements.txt)

## Development Setup

1. Clone the repository.
2. Install Python 3.13.3.
3. Create and activate a virtual environment.
```bash
python -m venv .venv
source .venv/bin/activate
```
4. Install the dependencies.
```bash
pip install -r requirements.txt
```
5. Install Node.js.
6. Run database migrations.
```bash
python manage.py migrate
```
7. Run the development server.
```bash
python manage.py runserver
```
8. Optional: create a superuser.
```bash
python manage.py createsuperuser
```

## Before You Commit (IMPORTANT)

Before you commit, run the following commands to ensure your code is clean and ready to be committed.

```bash
./auto_fix.sh

# Don't forget to run the tests!
python -m pytest
```

## Deployment Instructions

* TODO

## Testing
```bash
# Run all tests
python -m pytest

# Run only API tests
python -m pytest -k "api or API"

# Run tests for specific app
python -m pytest <app_name>/
```

## Running Multiple Nodes Locally

To test the distributed features of the application locally, you can run multiple instances of the Django server.

The project is already configured to use a separate SQLite database file for each node based on the `DB_NAME` environment variable. This was done by modifying `socialdistribution/settings.py`.

### 1. Launching the Nodes

**Terminal 1: Run Node 1**
```bash
# Activate the virtual environment
source .venv/bin/activate

# Create and migrate the database for Node 1
DB_NAME=node1.sqlite3 python manage.py migrate

# Run the server for Node 1 on port 8000
DB_NAME=node1.sqlite3 python manage.py runserver 8000
```

**Terminal 2: Run Node 2**
```bash
source .venv/bin/activate
DB_NAME=node2.sqlite3 python manage.py migrate
DB_NAME=node2.sqlite3 python manage.py runserver 8001
```

Repeat this for more nodes as needed.

### 2. Connecting the Nodes

Once the nodes are running, you must register them with each other so they can communicate.

1.  **Create Admin Users**:
    ```bash
    # For Node 1
    DB_NAME=node1.sqlite3 python manage.py createsuperuser

    # For Node 2
    DB_NAME=node2.sqlite3 python manage.py createsuperuser
    ```

2.  **Log in to the Admin Panels**

3.  **Register Remote Nodes**:
    - In Node 1's admin panel, navigate to "Remote nodes" and add a new entry.
        - **Host**: `http://127.0.0.1:8001/`
        - **Username/Password**: The credentials Node 1 will use to log into Node 2.
    - In Node 2's admin panel, do the reverse. Add a "Remote node" for Node 1.
        - **Host**: `http://127.0.0.1:8000/`
        - **Username/Password**: The credentials Node 2 will use to log into Node 1.

Done!

## Deploying to Heroku
See this [heroku article](https://devcenter.heroku.com/articles/git) to setup an app via heroku CLI or follow the instructions below. First create a heroku app.

```bash
heroku create <app-name>
```

Or add remote to an existing repository to an existing app using

```bash
 heroku git:remote -a example-app
```

Afterwards, add the npm webpack to enable building of javascript files via `esbuild` and enable postgreSQL. 

```bash
heroku buildpacks:add --index 1 heroku/nodejs --app <app-name>
heroku addons:create heroku-postgresql:essential-0 --app <app-name>
```

Finally, deploy code to the heroku app.
```bash
git push heroku <local-branch>:<remote-branch>
```

Installation of dependencies and post build scripts will automatically run after each push to the heroku remote. After a successful build, the heroku instance should be available online. Django commands can be ran to create super users and migrate using `heroku run`.

```bash
heroku run "python manage.py createsuperuser" --app <app-name>
heroku run "python manage.py migrate" --app <app-name>
```


## API Documentation

The API for this project is documented using OpenAPI 3. You can access the interactive documentation through the following endpoints when the server is running:

- **Swagger UI**: [`/api/schema/swagger-ui/`](/api/schema/swagger-ui/) - A rich, interactive UI for exploring the API.
- **Redoc**: [`/api/schema/redoc/`](/api/schema/redoc/) - An alternative, clean, and readable documentation format.
- **Schema JSON**: [`/api/schema/`](/api/schema/) - The raw OpenAPI schema in JSON format.

## Quality Checks
On every push or pull request, this repo runs:

**Python**
- **PEP8 style check** via `autopep8`
- **Linting** via `flake8`
- **Type checking** via `mypy`

**JavaScript**
- [JavaScript Standard Style](https://standardjs.com/) to maintain a consistent code style.

**HTML**
- **W3C Validation** via `html-w3c-validator`.

**CSS**
- **CSS Validation** via `css-validator` (W3C).

If the CI jobs fail, first make the script executable by running `chmod +x ./auto_fix.sh`, then run `./auto_fix.sh` on your local code and then commiting again may fix things.
