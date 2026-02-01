"""
MpyTool - Sublime Text plugin for MicroPython development

Provides integration with mpytool CLI for uploading, downloading,
and running code on MicroPython devices.
"""
import sublime
import sublime_plugin
import subprocess
import sys
import threading
import json
import os
import re


def find_mpyproject(path):
    """Find .mpyproject searching upward from path"""
    if not path:
        return None

    directory = path if os.path.isdir(path) else os.path.dirname(path)

    while directory and directory != os.path.dirname(directory):
        # Skip .backup directories (may contain .mpyproject from device)
        if os.path.basename(directory) == '.backup':
            directory = os.path.dirname(directory)
            continue
        candidate = os.path.join(directory, '.mpyproject')
        if os.path.exists(candidate):
            return candidate
        directory = os.path.dirname(directory)
    return None


def load_mpyproject(path):
    """Load .mpyproject, return {} if empty"""
    try:
        with open(path, 'r') as f:
            content = f.read().strip()
            if not content:
                return {}
            # Remove trailing commas (not valid JSON but common)
            content = re.sub(r',\s*([}\]])', r'\1', content)
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return {}


def get_project_root(mpyproject_path):
    """Return directory containing .mpyproject"""
    return os.path.dirname(mpyproject_path)


class MpyContext:
    """Context for current MicroPython project"""

    _current = None  # manually selected project

    @classmethod
    def get(cls, view):
        """Get context for view"""
        # 1. Manually selected
        if cls._current and os.path.exists(cls._current):
            return cls._current

        # 2. Search from active file
        if view and view.file_name():
            found = find_mpyproject(view.file_name())
            if found:
                return found

        # 3. Search in open folders
        window = view.window() if view else sublime.active_window()
        if window:
            for folder in window.folders():
                found = find_mpyproject(folder)
                if found:
                    return found

        return None

    @classmethod
    def set(cls, path):
        """Manually set project"""
        cls._current = path

    @classmethod
    def clear(cls):
        """Clear manual selection"""
        cls._current = None


class MpyProcessManager:
    """Manages running mpytool process"""
    _process = None

    @classmethod
    def set(cls, process):
        cls.stop()
        cls._process = process

    @classmethod
    def stop(cls):
        if cls._process and cls._process.poll() is None:
            cls._process.terminate()
            cls._process = None

    @classmethod
    def is_running(cls):
        return cls._process is not None and cls._process.poll() is None


class MpyToolCommand(sublime_plugin.WindowCommand):
    """Base class for mpytool commands"""

    panel_name = 'mpytool'
    _panel = None

    def get_context(self, required=True):
        """Get .mpyproject and its config"""
        view = self.window.active_view()
        mpyproject = MpyContext.get(view)

        if not mpyproject:
            if required:
                sublime.error_message("No .mpyproject file found")
            return None, None

        config = load_mpyproject(mpyproject)
        return mpyproject, config

    def get_port(self):
        """Get port from config or 'auto'"""
        mpyproject, config = self.get_context(required=False)
        if config:
            return config.get('port', 'auto')
        return 'auto'

    def get_panel(self, clear=False):
        """Get or create output panel"""
        if clear or MpyToolCommand._panel is None:
            MpyToolCommand._panel = self.window.create_output_panel(self.panel_name)
        return MpyToolCommand._panel

    def show_panel(self):
        """Show output panel"""
        self.window.run_command(
            'show_panel', {'panel': f'output.{self.panel_name}'})

    def append_output(self, text):
        """Append text to output panel"""
        panel = self.get_panel()
        panel.run_command('append', {'characters': text})

    def run_mpytool(self, args, cwd=None):
        """Run mpytool in background thread"""
        settings = sublime.load_settings('mpytool.sublime-settings')
        mpytool_path = settings.get('mpytool_path', 'mpytool')

        cmd = [mpytool_path] + args

        self.get_panel(clear=True)
        self.show_panel()
        self.append_output(f"$ {' '.join(cmd)}\n")

        thread = threading.Thread(
            target=self._run_process,
            args=(cmd, cwd))
        thread.start()

    def _run_process(self, cmd, cwd):
        """Run process and stream output"""
        try:
            # Stop any running process first
            MpyProcessManager.stop()

            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True)

            MpyProcessManager.set(process)

            output_lines = []
            for line in process.stdout:
                output_lines.append(line)
                sublime.set_timeout(
                    lambda l=line: self.append_output(l), 0)

            process.wait()

            # Check for multiple ports error
            output = ''.join(output_lines)
            if 'Multiple serial ports found' in output:
                ports = self._parse_ports(output)
                if ports:
                    sublime.set_timeout(
                        lambda: self._show_port_selection(cmd, cwd, ports), 0)
                    return

            sublime.set_timeout(
                lambda: self.append_output(
                    f"\n[Finished with code {process.returncode}]\n"), 0)

            # Update status bar
            sublime.set_timeout(lambda: self._update_status(), 0)

        except FileNotFoundError:
            sublime.set_timeout(
                lambda: sublime.error_message(
                    f"mpytool not found: {cmd[0]}"), 0)

    def _parse_ports(self, output):
        """Parse port list from mpytool error output"""
        ports = []
        in_ports = False
        for line in output.split('\n'):
            if 'Multiple serial ports found' in line:
                in_ports = True
                continue
            if in_ports and line.strip().startswith('/dev/'):
                ports.append(line.strip())
            elif in_ports and line.strip() and not line.strip().startswith('/dev/'):
                break
        return ports

    def _show_port_selection(self, cmd, cwd, ports):
        """Show quick panel to select port"""
        def on_select(index):
            if index >= 0:
                # Insert -p port after mpytool command
                new_cmd = [cmd[0], '-p', ports[index]] + cmd[1:]
                self.get_panel(clear=True)
                self.show_panel()
                self.append_output(f"$ {' '.join(new_cmd)}\n")
                thread = threading.Thread(
                    target=self._run_process,
                    args=(new_cmd, cwd))
                thread.start()

        self.window.show_quick_panel(ports, on_select)

    def _update_status(self):
        """Update status bar"""
        view = self.window.active_view()
        if view:
            view.run_command('mpy_update_status')


class MpySyncCommand(MpyToolCommand):
    """Sync to Device: upload files and reset"""

    def run(self):
        self._run_sync(monitor=False)

    def _run_sync(self, monitor=False):
        mpyproject, config = self.get_context()
        if not mpyproject:
            return

        root = get_project_root(mpyproject)
        port = config.get('port', 'auto')

        # Get deploy config: {"/": ["./"], "/lib/": ["../x.py"]}
        # Default: deploy entire project to /
        deploy = config.get('deploy') or {"/": ["./"]}

        args = []

        if port != 'auto':
            args.extend(['-p', port])

        # Add exclude patterns
        exclude = config.get('exclude', [])
        for pattern in exclude:
            args.extend(['-e', pattern])

        # Build command: cp src1 src2 :dest1 -- cp src3 :dest2 -- ...
        first = True
        for dest, sources in deploy.items():
            if not sources:
                continue

            # Normalize dest
            if not dest.startswith('/'):
                dest = '/' + dest

            if not first:
                args.append('--')
            args.append('cp')
            args.extend(sources)
            args.append(f':{dest}')
            first = False

        if first:
            # No files to deploy
            sublime.error_message("Nothing to deploy. Configure 'deploy' in .mpyproject")
            return

        args.extend(['--', 'reset'])

        if monitor:
            args.extend(['--', 'monitor'])

        self.run_mpytool(args, cwd=root)


class MpyDeployCommand(MpySyncCommand):
    """Deploy to Device: upload, reset, and monitor"""

    def run(self):
        self._run_sync(monitor=True)


class MpyStopCommand(sublime_plugin.WindowCommand):
    """Stop running mpytool process"""

    def run(self):
        MpyProcessManager.stop()
        sublime.status_message("MpyTool: stopped")

    def is_enabled(self):
        return MpyProcessManager.is_running()


def find_backup_in_path(path):
    """Find .backup in path or as subdirectory, return backup path or None"""
    # Check if .backup is in the path
    parts = path.split(os.sep)
    for i, part in enumerate(parts):
        if part == '.backup':
            return os.sep.join(parts[:i + 1])
    # Check if .backup exists as subdirectory
    backup_subdir = os.path.join(path, '.backup')
    if os.path.isdir(backup_subdir):
        return backup_subdir
    return None


class MpyBackupCommand(MpyToolCommand):
    """Backup device to local folder"""

    def run(self):
        self._port = self.get_port()

        # Get current directory
        view = self.window.active_view()
        if view and view.file_name():
            current_dir = os.path.dirname(view.file_name())
        elif self.window.folders():
            current_dir = self.window.folders()[0]
        else:
            current_dir = os.path.expanduser('~')

        # Use existing .backup or create new one
        default_path = find_backup_in_path(current_dir)
        if not default_path:
            default_path = os.path.join(current_dir, '.backup')

        self.window.show_input_panel(
            "Backup to:",
            default_path,
            self._on_done,
            None,
            None)

    def _on_done(self, path):
        if not path:
            return

        # Create directory if needed
        if not os.path.exists(path):
            os.makedirs(path)

        args = []
        if self._port != 'auto':
            args.extend(['-p', self._port])

        args.extend(['cp', ':/', path])

        self.run_mpytool(args)


class MpyRestoreCommand(MpyToolCommand):
    """Restore backup to device"""

    def _get_backup_path(self):
        """Get backup path from current location or None"""
        view = self.window.active_view()
        if view and view.file_name():
            current_dir = os.path.dirname(view.file_name())
        elif self.window.folders():
            current_dir = self.window.folders()[0]
        else:
            return None
        return find_backup_in_path(current_dir)

    def run(self):
        backup_path = self._get_backup_path()
        if not backup_path:
            sublime.error_message("No .backup directory found")
            return

        self._port = self.get_port()

        self.window.show_input_panel(
            "Restore from:",
            backup_path,
            self._on_done,
            None,
            None)

    def is_enabled(self):
        return self._get_backup_path() is not None

    def _on_done(self, path):
        if not path:
            return

        if not os.path.exists(path):
            sublime.error_message(f"Directory not found: {path}")
            return

        args = []
        if self._port != 'auto':
            args.extend(['-p', self._port])

        # Upload contents of backup folder to device root
        args.extend(['cp', path + '/', ':/'])

        self.run_mpytool(args)


class MpyTreeCommand(MpyToolCommand):
    """Show file tree on device"""

    def run(self):
        port = self.get_port()

        args = []
        if port != 'auto':
            args.extend(['-p', port])

        args.append('tree')

        self.run_mpytool(args)


class MpyInfoCommand(MpyToolCommand):
    """Show device info"""

    def run(self):
        port = self.get_port()

        args = []
        if port != 'auto':
            args.extend(['-p', port])

        args.append('info')

        self.run_mpytool(args)


class MpyEraseDeviceCommand(MpyToolCommand):
    """Remove all files from device"""

    def run(self):
        if not sublime.ok_cancel_dialog(
                "Remove ALL files from device?",
                "Remove All"):
            return

        port = self.get_port()

        args = []
        if port != 'auto':
            args.extend(['-p', port])

        args.extend(['rm', '/'])

        self.run_mpytool(args)


class MpyReplCommand(MpyToolCommand):
    """Open REPL"""

    _terminus_tag = "mpytool_repl"

    def run(self):
        port = self.get_port()

        settings = sublime.load_settings('mpytool.sublime-settings')
        mpytool_path = settings.get('mpytool_path', 'mpytool')

        args = []
        if port != 'auto':
            args.extend(['-p', port])
        args.append('repl')

        cmd = [mpytool_path] + args

        # Try Terminus first
        if self._try_terminus(cmd):
            return

        # Fallback to external terminal
        if sublime.platform() == 'osx':
            script = f'tell app "Terminal" to do script "{" ".join(cmd)}"'
            subprocess.run(['osascript', '-e', script])
        elif sublime.platform() == 'linux':
            subprocess.Popen(['x-terminal-emulator', '-e'] + cmd)

    def _try_terminus(self, cmd):
        """Try to open REPL in Terminus. Returns True if successful."""
        # Check if existing REPL is open - focus it
        for view in self.window.views():
            if view.settings().get("terminus_view.tag") == self._terminus_tag:
                self.window.focus_view(view)
                return True

        # Check if Terminus is available
        if "Terminus" not in sys.modules:
            try:
                sublime.find_resources("Terminus.sublime-settings")
            except Exception:
                return False
            # Check if command exists
            if not self.window.find_output_panel("Terminus"):
                pass  # OK, just means no panel yet

        # Try to open new Terminus
        try:
            self.window.run_command("terminus_open", {
                "cmd": cmd,
                "title": "MicroPython REPL",
                "auto_close": True,
                "tag": self._terminus_tag,
            })
            return True
        except Exception:
            return False


class MpyResetCommand(MpyToolCommand):
    """Reset device"""

    def run(self, monitor=False):
        port = self.get_port()

        args = []
        if port != 'auto':
            args.extend(['-p', port])

        args.append('reset')

        if monitor:
            args.extend(['--', 'monitor'])

        self.run_mpytool(args)


class MpyMonitorCommand(MpyToolCommand):
    """Monitor device output"""

    def run(self):
        port = self.get_port()

        args = []
        if port != 'auto':
            args.extend(['-p', port])

        args.append('monitor')

        self.run_mpytool(args)


class MpyNewProjectCommand(sublime_plugin.WindowCommand):
    """Create new .mpyproject file"""

    def run(self, paths=None):
        # Determine initial directory
        if paths:
            # From sidebar context menu
            path = paths[0]
            directory = path if os.path.isdir(path) else os.path.dirname(path)
        else:
            # From command palette
            view = self.window.active_view()
            if view and view.file_name():
                directory = os.path.dirname(view.file_name())
            elif self.window.folders():
                directory = self.window.folders()[0]
            else:
                directory = os.path.expanduser("~")

        initial_path = os.path.join(directory, ".mpyproject")

        self.window.show_input_panel(
            "Create .mpyproject:",
            initial_path,
            self._on_done,
            None,
            None)

    def _on_done(self, path):
        """Create the .mpyproject file"""
        if not path:
            return

        # Ensure it ends with .mpyproject
        if not path.endswith(".mpyproject"):
            path = os.path.join(path, ".mpyproject")

        # Check if already exists
        if os.path.exists(path):
            if not sublime.ok_cancel_dialog(f"{path}\n\nFile already exists. Overwrite?"):
                return

        # Create directory if needed
        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory)

        # Create .mpyproject with name from directory
        project_name = os.path.basename(directory)
        config = {"name": project_name}
        with open(path, 'w') as f:
            json.dump(config, f, indent=4)
            f.write('\n')

        # Set as current project
        MpyContext.set(path)

        # Update status and show message
        view = self.window.active_view()
        if view:
            view.run_command('mpy_update_status')

        sublime.status_message(f"Created {path}")

    def is_visible(self, paths=None):
        """Show only if no .mpyproject exists in path or parents"""
        if not paths:
            return True  # Always show in command palette

        path = paths[0]
        directory = path if os.path.isdir(path) else os.path.dirname(path)
        return find_mpyproject(directory) is None


def save_mpyproject(path, config):
    """Save config to .mpyproject file"""
    with open(path, 'w') as f:
        json.dump(config, f, indent=4)
        f.write('\n')


def add_to_deploy(mpyproject, rel_path, dest, add_default=False):
    """Add file/folder to deploy config"""
    config = load_mpyproject(mpyproject)
    deploy = config.get('deploy')

    # If deploy was empty/missing and add_default is True, add default first
    if not deploy:
        deploy = {"/": ["./"]} if add_default else {}

    # Normalize dest
    if not dest.startswith('/'):
        dest = '/' + dest

    if dest not in deploy:
        deploy[dest] = []

    if rel_path in deploy[dest]:
        sublime.status_message(f"'{rel_path}' already in deploy[{dest}]")
        return

    deploy[dest].append(rel_path)
    config['deploy'] = deploy
    save_mpyproject(mpyproject, config)
    sublime.status_message(f"Added '{rel_path}' to deploy[{dest}]")


class MpyAddToDeployCommand(sublime_plugin.WindowCommand):
    """Add file/folder to project deploy config"""

    _add_default = False  # Override in subclass

    def run(self, paths=None):
        if not paths:
            return

        self._path = paths[0]
        self._is_dir = os.path.isdir(self._path)
        self._mpyproject = find_mpyproject(self._path)
        if not self._mpyproject:
            return

        root = get_project_root(self._mpyproject)
        self._rel_path = os.path.relpath(self._path, root)

        self._show_dest_selection()

    def _show_dest_selection(self):
        """Show quick panel with destination options"""
        config = load_mpyproject(self._mpyproject)
        deploy = config.get('deploy') or {}

        # Build options: "/" first, existing paths, "Custom..." last
        self._dest_options = ["/"]
        for dest in deploy.keys():
            if dest != "/" and dest not in self._dest_options:
                self._dest_options.append(dest)
        self._dest_options.append("Custom...")

        self.window.show_quick_panel(self._dest_options, self._on_dest_select)

    def _on_dest_select(self, index):
        if index < 0:
            return

        if self._dest_options[index] == "Custom...":
            # Show input panel for custom path
            self.window.show_input_panel(
                "Device path:",
                "/",
                self._on_custom_dest,
                None,
                None)
        else:
            self._finish(self._dest_options[index])

    def _on_custom_dest(self, dest):
        if dest is None:
            return
        self._finish(dest or "/")

    def _finish(self, dest):
        add_to_deploy(self._mpyproject, self._rel_path, dest, add_default=self._add_default)

    def is_visible(self, paths=None):
        if not paths:
            return False
        return find_mpyproject(paths[0]) is not None


class MpyAddToExcludeCommand(sublime_plugin.WindowCommand):
    """Add file/folder to project exclude list"""

    def run(self, paths=None):
        if not paths:
            return

        path = paths[0]
        mpyproject = find_mpyproject(path)
        if not mpyproject:
            return

        root = get_project_root(mpyproject)
        rel_path = os.path.relpath(path, root)

        config = load_mpyproject(mpyproject)
        exclude = config.get('exclude', [])

        if rel_path in exclude:
            sublime.status_message(f"'{rel_path}' already in exclude")
            return

        exclude.append(rel_path)
        config['exclude'] = exclude
        save_mpyproject(mpyproject, config)
        sublime.status_message(f"Added '{rel_path}' to exclude")

    def is_visible(self, paths=None):
        if not paths:
            return False
        return find_mpyproject(paths[0]) is not None


class MpyCopyToDeviceCommand(MpyToolCommand):
    """Copy file or folder to device"""

    def run(self, paths=None):
        if not paths:
            return

        self._path = paths[0]
        self._is_folder = os.path.isdir(self._path)
        self._port = self.get_port()

        self.window.show_input_panel(
            "Device path:",
            "/",
            self._on_done,
            None,
            None)

    def _on_done(self, dest):
        if dest is None:
            return

        if not dest.startswith('/'):
            dest = '/' + dest

        args = []
        if self._port != 'auto':
            args.extend(['-p', self._port])

        src = self._path + '/' if self._is_folder else self._path
        args.extend(['cp', src, ':' + dest])
        self.run_mpytool(args)


class MpyAddToOtherProjectCommand(sublime_plugin.WindowCommand):
    """Add file/folder to another project's deploy config"""

    def run(self, paths=None):
        if not paths:
            return

        self._path = paths[0]
        self._is_dir = os.path.isdir(self._path)

        # Find all projects
        self._projects = []
        for folder in self.window.folders():
            for root, dirs, files in os.walk(folder):
                if '.mpyproject' in files:
                    self._projects.append(os.path.join(root, '.mpyproject'))
                dirs[:] = [d for d in dirs if not d.startswith('.')]

        if not self._projects:
            sublime.error_message("No .mpyproject found")
            return

        # Show project selection
        items = [os.path.dirname(p) for p in self._projects]
        self.window.show_quick_panel(items, self._on_project_select)

    def _on_project_select(self, index):
        if index < 0:
            return

        self._mpyproject = self._projects[index]
        self._root = get_project_root(self._mpyproject)
        self._rel_path = os.path.relpath(self._path, self._root)

        self._show_dest_selection()

    def _show_dest_selection(self):
        """Show quick panel with destination options"""
        config = load_mpyproject(self._mpyproject)
        deploy = config.get('deploy') or {}

        # Build options: "/" first, existing paths, "Custom..." last
        self._dest_options = ["/"]
        for dest in deploy.keys():
            if dest != "/" and dest not in self._dest_options:
                self._dest_options.append(dest)
        self._dest_options.append("Custom...")

        self.window.show_quick_panel(self._dest_options, self._on_dest_select)

    def _on_dest_select(self, index):
        if index < 0:
            return

        if self._dest_options[index] == "Custom...":
            self.window.show_input_panel(
                "Device path:",
                "/",
                self._on_custom_dest,
                None,
                None)
        else:
            self._finish(self._dest_options[index])

    def _on_custom_dest(self, dest):
        if dest is None:
            return
        self._finish(dest or "/")

    def _finish(self, dest):
        add_to_deploy(self._mpyproject, self._rel_path, dest, add_default=True)
        project_name = os.path.basename(self._root)
        sublime.status_message(f"Added '{self._rel_path}' to {project_name}")

    def is_visible(self, paths=None):
        if not paths:
            return False
        # Check if any project exists
        for folder in self.window.folders():
            for root, dirs, files in os.walk(folder):
                if '.mpyproject' in files:
                    return True
                dirs[:] = [d for d in dirs if not d.startswith('.')]
        return False


class MpySetActiveCommand(sublime_plugin.WindowCommand):
    """Set project as active from sidebar"""

    def run(self, paths=None):
        if not paths:
            return

        mpyproject = self._get_mpyproject(paths[0])
        if mpyproject:
            MpyContext.set(mpyproject)
            view = self.window.active_view()
            if view:
                view.run_command('mpy_update_status')
            project_name = os.path.basename(os.path.dirname(mpyproject))
            sublime.status_message(f"Active project: {project_name}")

    def _get_mpyproject(self, path):
        """Get .mpyproject path from file or folder"""
        # Clicked on .mpyproject file
        if os.path.basename(path) == '.mpyproject':
            return path
        # Clicked on folder containing .mpyproject
        if os.path.isdir(path):
            candidate = os.path.join(path, '.mpyproject')
            if os.path.exists(candidate):
                return candidate
        return None

    def is_visible(self, paths=None):
        if not paths:
            return False
        return self._get_mpyproject(paths[0]) is not None


class MpySelectProjectCommand(sublime_plugin.WindowCommand):
    """Manual project selection"""

    def run(self):
        projects = []

        for folder in self.window.folders():
            for root, dirs, files in os.walk(folder):
                if '.mpyproject' in files:
                    projects.append(os.path.join(root, '.mpyproject'))
                dirs[:] = [d for d in dirs if not d.startswith('.')]

        if not projects:
            sublime.error_message("No .mpyproject found")
            return

        # Get current context
        view = self.window.active_view()
        current = MpyContext.get(view) if view else None
        is_manual = MpyContext._current is not None

        # Build items list
        items = []
        self._projects = [None]  # None = auto mode

        # First option: Auto mode
        auto_label = "● Auto (from current file)" if not is_manual else "Auto (from current file)"
        items.append([auto_label, "Clear manual selection"])

        # Project options
        for p in projects:
            project_dir = os.path.dirname(p)
            project_name = os.path.basename(project_dir)
            if p == current and is_manual:
                label = f"● {project_name}"
            else:
                label = f"  {project_name}"
            items.append([label, project_dir])
            self._projects.append(p)

        def on_select(index):
            if index < 0:
                return
            if index == 0:
                # Auto mode
                MpyContext.clear()
            else:
                MpyContext.set(self._projects[index])

            view = self.window.active_view()
            if view:
                view.run_command('mpy_update_status')

        self.window.show_quick_panel(items, on_select)


class MpyUpdateStatusCommand(sublime_plugin.TextCommand):
    """Update status bar"""

    def run(self, edit):
        mpyproject = MpyContext.get(self.view)

        if mpyproject:
            project_name = os.path.basename(os.path.dirname(mpyproject))
            self.view.set_status('mpytool', f'MPY: {project_name}')
        else:
            self.view.erase_status('mpytool')


def plugin_loaded():
    """Called by Sublime when plugin is loaded"""
    print("MpyTool: plugin loaded")


class MpyEventListener(sublime_plugin.EventListener):
    """Event listener for automatic actions"""

    def on_activated(self, view):
        """Update status bar when switching tabs"""
        view.run_command('mpy_update_status')

    def on_window_command(self, window, command_name, args):
        """Stop monitor when panel is hidden"""
        if command_name == 'hide_panel':
            panel = args.get('panel', '') if args else ''
            if panel == 'output.mpytool' or panel == '':
                MpyProcessManager.stop()
