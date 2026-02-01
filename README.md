# MpyTool - Sublime Text Plugin

Sublime Text 4 plugin for MicroPython development using [mpytool](https://github.com/pfalcon/mpytool).

## Installation

### Symlink (recommended for development)

```bash
# macOS
ln -s /path/to/mpytool-sublime ~/Library/Application\ Support/Sublime\ Text/Packages/mpytool

# Linux
ln -s /path/to/mpytool-sublime ~/.config/sublime-text/Packages/mpytool
```

### Manual

Copy folder to Sublime Text Packages directory and rename to `mpytool`:

- **macOS**: `~/Library/Application Support/Sublime Text/Packages/`
- **Linux**: `~/.config/sublime-text/Packages/`

## Quick Start

1. Open Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`)
2. Run `MPY: New Project...` to create `.mpyproject` in your project root
3. Use `MPY: Deploy to Device` to upload and run

## Commands

| Command | Description |
|---------|-------------|
| **Deploy to Device** | Upload files + reset + monitor |
| **Sync to Device** | Upload files + reset |
| **List Files** | Show file tree on device |
| **Erase Device** | Remove all files from device |
| **Reset Device** | Soft reset |
| **Reset and Monitor** | Reset + watch serial output |
| **Monitor** | Watch serial output |
| **Open REPL** | Interactive console (Terminus or external terminal) |
| **Backup Device** | Download all files to `.backup/` |
| **Restore Backup** | Upload `.backup/` to device |
| **New Project...** | Create `.mpyproject` file |
| **Select Project...** | Choose active project |
| **Stop** | Stop running process |

## Keyboard Shortcuts

| macOS | Windows/Linux | Command |
|-------|---------------|---------|
| `Cmd+Shift+D` | `Ctrl+Shift+D` | Deploy to Device |
| `Cmd+Shift+L` | `Ctrl+Shift+L` | List Files |

## Sidebar Context Menu

Right-click on files/folders in sidebar → **MicroPython**:

- **Copy to Device...** - Upload file or folder to device
- **New Project...** - Create new project here
- **Set as Active Project** - Set this project as active
- **Add to Deploy** - Add to deploy configuration
- **Add to Exclude** - Add to exclude list
- **Add to Other Project...** - Add to another project's deploy

## Configuration

### .mpyproject

```json
{
    "name": "my-project",
    "port": "auto",
    "deploy": {
        "/": ["./"],
        "/lib/": ["../external-lib.py"]
    },
    "exclude": ["__pycache__", "*.pyc", ".backup"]
}
```

| Field | Description |
|-------|-------------|
| `name` | Project name (shown in status bar) |
| `port` | Serial port or `"auto"` for auto-detection |
| `deploy` | Map of device paths to local sources |
| `exclude` | Patterns to exclude from upload |

### Deploy Examples

```json
// Upload entire project to device root
"deploy": {
    "/": ["./"]
}

// Upload specific files to specific locations
"deploy": {
    "/": ["main.py", "boot.py"],
    "/lib/": ["lib/", "../shared/utils.py"]
}
```

### Plugin Settings

Edit `mpytool.sublime-settings`:

```json
{
    "mpytool_path": "mpytool"
}
```

## Features

- **Auto-detection** - Finds `.mpyproject` from current file upward
- **Manual selection** - Switch between multiple projects
- **Port selection** - Prompts when multiple devices connected
- **Status bar** - Shows active project name
- **Terminus integration** - REPL in Sublime Text (falls back to external terminal)

## Requirements

- Sublime Text 4 (build 4065+)
- [mpytool](https://github.com/pfalcon/mpytool) CLI installed
- Optional: [Terminus](https://packagecontrol.io/packages/Terminus) for in-editor REPL
