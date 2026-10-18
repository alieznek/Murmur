from __future__ import annotations

import os
import copy
import json
import sys
import tempfile
import uuid
from pathlib import Path


class ConfigurationError(RuntimeError):
    pass


DEFAULT_APPEARANCE = {
    "theme": "light", "ui_font": "Segoe UI", "source_font": "Microsoft YaHei UI",
    "result_font": "Georgia", "source_size": 14, "result_size": 27, "line_height": 1.7,
}


def validate_appearance(values: dict) -> dict:
    if not isinstance(values, dict) or any(key not in DEFAULT_APPEARANCE for key in values):
        raise ConfigurationError("字体与外观设置不受支持。")
    result = {**DEFAULT_APPEARANCE, **values}
    if result["theme"] not in ("light", "dark"):
        raise ConfigurationError("请选择有效的主题。")
    for key in ("ui_font", "source_font", "result_font"):
        if not isinstance(result[key], str) or not result[key].strip() or len(result[key]) > 80 or any(c in result[key] for c in "\r\n\"';{}"):
            raise ConfigurationError("请选择有效的字体。")
    for key, lower, upper in (("source_size", 11, 24), ("result_size", 16, 38)):
        if type(result[key]) is not int or not lower <= result[key] <= upper:
            raise ConfigurationError("字号超出支持范围。")
    if type(result["line_height"]) not in (int, float) or not 1.3 <= result["line_height"] <= 2.2:
        raise ConfigurationError("请选择有效的行间距。")
    return result


def user_config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    return base / "Murmur" / "settings.json"


class SystemCredentialStore:
    """Use only a native credential backend; never fall back to a plaintext plugin."""

    SERVICE = "Murmur"  # Stable namespace for stored system credentials.

    def _backend(self):
        try:
            if sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring
                return WinVaultKeyring()
            if sys.platform == "darwin":
                from keyring.backends.macOS import Keyring
                return Keyring()
            from keyring.backends.SecretService import Keyring
            return Keyring()
        except Exception:
            raise ConfigurationError("系统凭据存储不可用。请检查 keyring 安装和系统凭据服务；不会改用明文保存。") from None

    def get(self, name: str) -> str | None:
        try:
            return self._backend().get_password(self.SERVICE, name)
        except Exception:
            raise ConfigurationError("无法读取系统凭据。请检查系统凭据服务后重试。") from None

    def set(self, name: str, value: str) -> None:
        try:
            self._backend().set_password(self.SERVICE, name, value)
        except Exception:
            raise ConfigurationError("无法保存系统凭据。请检查系统凭据服务；原配置保持不变。") from None

    def delete(self, name: str) -> None:
        try:
            backend = self._backend()
            if backend.get_password(self.SERVICE, name) is not None:
                backend.delete_password(self.SERVICE, name)
        except Exception:
            raise ConfigurationError("无法清除系统凭据。请检查系统凭据服务后重试。") from None


class SettingsStore:
    def __init__(self, path: Path | None = None, credentials=None):
        self.path = path or user_config_path()
        self.credentials = credentials or SystemCredentialStore()
        self.revision = 0
        self.cleanup_warning = ""

    def _read(self) -> dict:
        from screen_translator.services.providers import PROVIDERS

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema": 1, "active_provider": "", "providers": {}}
        except (OSError, ValueError):
            raise ConfigurationError("无法读取配置文件。请备份并修复 settings.json 后重试；程序不会覆盖损坏的配置。") from None
        try:
            if data["schema"] != 1 or not isinstance(data["providers"], dict):
                raise ValueError
            if not isinstance(data["active_provider"], str):
                raise ValueError
            if data.get("translation_mode") not in (None, "offline", "online"):
                raise ValueError
            if data.get("dock_side", "right") not in ("left", "right"):
                raise ValueError
            position = data.get("dock_position")
            if position is not None and (not isinstance(position, list) or len(position) != 2 or
                                         any(type(value) is not int or abs(value) > 1_000_000 for value in position)):
                raise ValueError
            if "appearance" in data:
                validate_appearance(data["appearance"])
            # Only supported services are configuration inputs. Discard unknown
            # profiles without resolving credentials or selecting a paid service.
            data["providers"] = {key: profile for key, profile in data["providers"].items() if key in PROVIDERS}
            if data["active_provider"] and data["active_provider"] not in PROVIDERS:
                data["active_provider"] = ""
                data["translation_mode"] = "offline"
            for provider_id, profile in data["providers"].items():
                provider = PROVIDERS[provider_id]
                if not isinstance(profile["options"], dict):
                    raise ValueError
                for key, value in profile["options"].items():
                    if key not in {field.key for field in provider.fields if not field.secret} or not isinstance(value, str):
                        raise ValueError
                reference = profile["credential_id"]
                if reference is not None and (not isinstance(reference, str) or
                                              not reference.startswith(provider_id + ":")):
                    raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ConfigurationError("配置版本或字段不受支持。请备份并修复 settings.json；原文件保持不变。") from None
        return data

    def _write(self, data: dict) -> None:
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="settings-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise ConfigurationError("配置文件保存失败。请检查用户配置目录的写入权限或磁盘空间后重试。") from None
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # Only non-sensitive JSON is ever written to this file.
        self.revision += 1

    @property
    def active_provider(self) -> str:
        data = self._read()
        if data["active_provider"]:
            return data["active_provider"]
        return "baidu"

    @property
    def translation_mode(self) -> str:
        data = self._read()
        if data.get("translation_mode"):
            return data["translation_mode"]
        # Preserve an existing explicit online preference, including a broken
        # credential reference. Failures must not silently switch services.
        if data["active_provider"]:
            return "online"
        return "offline"

    def set_translation_mode(self, mode: str) -> None:
        if mode not in ("offline", "online"):
            raise ConfigurationError("请选择有效的翻译模式。")
        data = self._read()
        data["translation_mode"] = mode
        self._write(data)

    @property
    def dock_side(self) -> str:
        return self._read().get("dock_side", "right")

    def set_dock_side(self, side: str) -> None:
        if side not in ("left", "right"):
            raise ConfigurationError("请选择左侧或右侧停靠。")
        data = self._read()
        data["dock_side"] = side
        data.pop("dock_position", None)
        self._write(data)

    @property
    def dock_position(self) -> list[int] | None:
        return self._read().get("dock_position")

    def set_dock_position(self, x: int, y: int) -> None:
        if any(type(value) is not int or abs(value) > 1_000_000 for value in (x, y)):
            raise ConfigurationError("浮动图标位置不受支持。")
        data = self._read()
        data["dock_position"] = [x, y]
        self._write(data)

    @property
    def appearance(self) -> dict:
        return validate_appearance(self._read().get("appearance", {}))

    def set_appearance(self, **values) -> None:
        data = self._read()
        data["appearance"] = validate_appearance({**data.get("appearance", {}), **values})
        self._write(data)

    def values(self, provider_id: str) -> dict[str, str]:
        from screen_translator.services.providers import get_provider

        provider = get_provider(provider_id)
        profile = self._read()["providers"].get(provider_id)
        values = {field.key: field.default for field in provider.fields}
        if profile is None:
            return values
        values.update(profile["options"])
        reference = profile["credential_id"]
        if reference:
            raw = self.credentials.get(reference)
            if raw is None:
                raise ConfigurationError("系统凭据已丢失，请重新填写并保存该平台的凭据。")
            try:
                secret_values = json.loads(raw)
                if not isinstance(secret_values, dict) or any(not isinstance(v, str) for v in secret_values.values()):
                    raise ValueError
                values.update({field.key: secret_values.get(field.key, "") for field in provider.fields if field.secret})
            except (ValueError, TypeError):
                raise ConfigurationError("系统凭据格式不正确，请重新填写并保存该平台的凭据。") from None
        return values

    def save(self, provider_id: str, values: dict[str, str], *, activate: bool = False) -> None:
        from screen_translator.services.providers import get_provider

        provider = get_provider(provider_id)
        values = provider.validate(values)
        data = copy.deepcopy(self._read())
        previous = data["providers"].get(provider_id, {}).get("credential_id")
        reference = provider_id + ":" + uuid.uuid4().hex
        secret_values = {field.key: values[field.key] for field in provider.fields if field.secret}
        self.credentials.set(reference, json.dumps(secret_values, ensure_ascii=False))
        data["providers"][provider_id] = {
            "options": {field.key: values[field.key] for field in provider.fields if not field.secret},
            "credential_id": reference,
        }
        if activate:
            data["active_provider"] = provider_id
            data["translation_mode"] = "online"
        try:
            self._write(data)
        except ConfigurationError:
            try:
                self.credentials.delete(reference)
            except ConfigurationError:
                raise ConfigurationError("配置保存失败，原配置仍有效；临时凭据未能移除，请在 Windows 凭据管理器清理 Murmur 条目。") from None
            raise
        self.cleanup_warning = ""
        if previous:
            try:
                self.credentials.delete(previous)
            except ConfigurationError:
                self.cleanup_warning = "新配置已保存；旧凭据未能移除，请在 Windows 凭据管理器清理旧的 Murmur 条目。"

    def activate(self, provider_id: str) -> None:
        from screen_translator.services.providers import get_provider

        get_provider(provider_id).validate(self.values(provider_id))
        data = self._read()
        data["active_provider"] = provider_id
        data["translation_mode"] = "online"
        self._write(data)

    def clear(self, provider_id: str) -> None:
        from screen_translator.services.providers import get_provider

        get_provider(provider_id)
        data = self._read()
        profile = data["providers"].get(provider_id, {"options": {}, "credential_id": None})
        reference = profile["credential_id"]
        raw = self.credentials.get(reference) if reference else None
        if reference:
            self.credentials.delete(reference)
        data["providers"][provider_id] = {"options": profile["options"], "credential_id": None}
        try:
            self._write(data)
        except ConfigurationError:
            if reference and raw is not None:
                try:
                    self.credentials.set(reference, raw)
                except ConfigurationError:
                    raise ConfigurationError("配置写入失败且凭据恢复失败。原配置文件仍在，请重新填写该平台凭据。") from None
            raise
