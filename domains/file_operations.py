"""Safe file operations for the agent's isolated workspace."""

from __future__ import annotations

from pathlib import Path
import shutil

from utils.validator import SafetyError, WorkspaceGuard


class FileOperations:
    """Perform small, explicit filesystem operations inside one root folder."""

    def __init__(self, guard: WorkspaceGuard):
        self.guard = guard

    def _existing(self, value: str) -> Path:
        path = self.guard.path(value)
        if not path.exists():
            raise FileNotFoundError(f"Workspace path does not exist: {value}")
        return path

    def list_entries(self, value: str) -> list[dict[str, str | int]]:
        path = self._existing(value)
        if not path.is_dir():
            raise NotADirectoryError(f"Not a folder: {value}")

        entries: list[dict[str, str | int]] = []
        for entry in sorted(path.iterdir(), key=lambda item: item.name.lower()):
            if entry.is_symlink():
                kind = "symlink"
                size = 0
            elif entry.is_dir():
                kind = "directory"
                size = 0
            else:
                kind = "file"
                size = entry.stat().st_size
            entries.append(
                {
                    "name": entry.name,
                    "kind": kind,
                    "size": size,
                }
            )
        return entries

    def info(self, value: str) -> dict[str, str | int]:
        path = self._existing(value)
        if path.is_symlink():
            raise SafetyError("Symbolic links are not used by this agent.")
        kind = "directory" if path.is_dir() else "file"
        return {
            "path": self.guard.relative(path),
            "kind": kind,
            "size": 0 if path.is_dir() else path.stat().st_size,
        }

    def make_directory(self, value: str) -> str:
        path = self.guard.path(value)
        if path.exists():
            raise FileExistsError(f"Workspace path already exists: {value}")
        path.mkdir(parents=True, exist_ok=False)
        return self.guard.relative(path)

    def move(self, source_value: str, destination_value: str) -> str:
        source = self._existing(source_value)
        destination = self.guard.path(destination_value)

        if source == self.guard.root:
            raise SafetyError("The workspace root cannot be moved.")
        if source.is_symlink():
            raise SafetyError("Symbolic links cannot be moved.")
        if destination.exists() and destination.is_dir():
            final_path = destination / source.name
        else:
            final_path = destination
        if final_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing path: "
                f"{self.guard.relative(final_path)}"
            )
        if not final_path.parent.exists():
            raise FileNotFoundError(
                f"Destination folder does not exist: "
                f"{self.guard.relative(final_path.parent)}"
            )

        shutil.move(str(source), str(final_path))
        return self.guard.relative(final_path)

    def rename(self, source_value: str, new_name: str) -> str:
        source = self._existing(source_value)
        if source == self.guard.root:
            raise SafetyError("The workspace root cannot be renamed.")
        if source.is_symlink():
            raise SafetyError("Symbolic links cannot be renamed.")

        destination = source.parent / new_name
        if destination.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing path: "
                f"{self.guard.relative(destination)}"
            )
        source.rename(destination)
        return self.guard.relative(destination)

    def delete_file(self, value: str) -> str:
        path = self._existing(value)
        if path == self.guard.root:
            raise SafetyError("The workspace root cannot be deleted.")
        if path.is_dir():
            raise SafetyError(
                "FILE_DELETE only deletes files; empty folders require an explicit "
                "future command."
            )
        path.unlink()
        return self.guard.relative(path)
