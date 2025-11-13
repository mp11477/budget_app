# 🧱 BASIC GIT SETUP

| Command | Description |
|--------|-------------|
| `git init` | Initialize a new Git repo in current directory |
| `git config user.name "Your Name"` | Set your local Git username |
| `git config user.email "you@example.com"` | Set your local Git email |
| `git config --global user.name "Your Name"` | Set global username (across all projects) |
| `git config --global user.email "you@example.com"` | Set global email |

# 🔍 CHECKING STATUS & REMOTES

| Command | Description |
|--------|-------------|
| `git status` | See current branch, modified files, staged files |
| `git branch` | Show all branches, with `*` next to current one |
| `git remote -v` | View configured remotes (e.g., GitHub origin) |

# 🌿 BRANCHING

| Command | Description |
|--------|-------------|
| `git checkout -b sandbox` | Create and switch to a new branch called `sandbox` |
| `git checkout main` | Switch back to the `main` branch |
| `git branch -d sandbox` | Delete the `sandbox` branch (locally) |

# 💾 STAGING & COMMITTING

| Command | Description |
|--------|-------------|
| `git add .` | Stage all changes |
| `git add filename.py` | Stage a specific file |
| `git commit -m "Message"` | Commit staged changes with a message |

# ⬆️ PUSHING TO GITHUB

| Command | Description |
|--------|-------------|
| `git remote add origin https://github.com/user/repo.git` | Link local repo to remote |
| `git push -u origin main` | Push main branch and track it to GitHub |
| `git push -u origin sandbox` | Push a new branch (e.g., sandbox) and track it |
| `git push` | Push current branch to GitHub again after changes |

# ⬇️ PULLING FROM GITHUB

| Command | Description |
|--------|-------------|
| `git pull origin main` | Pull latest changes from `main` |
| `git pull --rebase origin main` | Pull and rebase (safer for syncing) |
| `git fetch` | Fetch remote changes, but don't merge |
| `git merge sandbox` | Merge `sandbox` into your current branch (e.g., `main`) |

# 🧹 FIXING COMMON ISSUES

| Command | Description |
|--------|-------------|
| `git rebase --continue` | Continue an in-progress rebase |
| `git rebase --abort` | Abort a broken rebase |
| `rm -rf .git` | 💣 Delete all Git history (start over!) *(⚠️ use with care)* |
| `echo venv/ > .gitignore` | Add files/folders to ignore list |
| `git rm --cached filename` | Remove a tracked file (useful after updating `.gitignore`) |

# 🧠 TIPS FOR YOU

- Your **main branch** is `main`, not `master`
- You now have a **sandbox branch** for testing changes before merging into `main`
- Use `git checkout -b feature/my-feature` for temporary ideas
- Always commit and push often, even when you're testing