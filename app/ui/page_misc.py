"""Диагностика, настройки и логи."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import diagnostics, winutils
from ..paths import APP_LOG, APP_VERSION, DATA_DIR, LOG_DIR, PROXY_LOG, ZAPRET_LOG
from . import icons
from .base import Page
from .fancy import ConfirmDialog
from .widgets import Card, Palette, Segmented, ToggleSwitch, button, label, row, run_bg, setting_row


class DiagnosticsPage(Page):
    title = "Диагностика"
    subtitle = "Поиск частых причин, по которым обход может не работать"

    def __init__(self, ctx):
        super().__init__(ctx)
        c = Card()
        c.lay.addLayout(row(button("Запустить диагностику", "primary", "pulse", self.run),
                            button("Очистить кэш Discord", "", "trash", self._discord,
                                   tip="Закрывает Discord и удаляет Cache, Code Cache, GPUCache"),
                            button("Сброс сети", "danger", "refresh", self._net_reset,
                                   tip="netsh winsock reset и др. — если не подходит ни одна стратегия"),
                            None))
        c.lay.addLayout(row(button("Добавить в исключения Защитника", "", "shield", self._defender,
                                   tip="Защитник Windows часто удаляет winws.exe и WinDivert — из-за этого "
                                       "обход перестаёт работать"),
                            button("Восстановить файлы zapret", "", "download", self._repair,
                                   tip="Вернуть winws.exe и WinDivert, если их удалил антивирус"),
                            None))
        self.status = label("Нажмите «Запустить диагностику»", "hint")
        c.lay.addWidget(self.status)
        self.list = QVBoxLayout()
        self.list.setSpacing(6)
        c.lay.addLayout(self.list)
        self.body.addWidget(c)
        self.finish()

    def run(self) -> None:
        self.status.setText("Проверка…")
        run_bg(lambda: diagnostics.run_all(self.ctx.zapret.root), self._show,
               lambda e: self.status.setText(f"Ошибка: {e}"))

    def _clear(self) -> None:
        while self.list.count():
            it = self.list.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _show(self, checks) -> None:
        self._clear()
        p = Palette.p
        errs = sum(1 for c in checks if c.level == diagnostics.ERR)
        warns = sum(1 for c in checks if c.level == diagnostics.WARN)
        self.status.setText(f"Готово: ошибок — {errs}, предупреждений — {warns}")
        for ch in sorted(checks, key=lambda c: {"err": 0, "warn": 1, "ok": 2}[c.level]):
            f = QFrame()
            f.setObjectName("diagRow")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(12, 9, 12, 9)
            lay.setSpacing(10)
            color = {"ok": p["on"], "warn": p["warn"], "err": p["err"]}[ch.level]
            ic = QLabel()
            ic.setPixmap(icons.pixmap({"ok": "check", "warn": "warn", "err": "x"}[ch.level], color, 18))
            lay.addWidget(ic, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(label(ch.title, wrap=True, selectable=True))
            if ch.detail:
                col.addWidget(label(ch.detail, "hint", wrap=True, selectable=True))
            lay.addLayout(col, 1)
            if ch.link:
                lay.addWidget(button("Подробнее", "link", "", lambda _=False, u=ch.link: winutils.open_url(u)))
            if ch.action:
                lay.addWidget(button(ch.action_label, "", "", lambda _=False, a=ch.action: self._action(a)))
            self.list.addWidget(f)

    def _action(self, a: str) -> None:
        fn = {"fix_windivert": diagnostics.fix_windivert, "remove_conflicts": diagnostics.remove_conflicts}[a]
        run_bg(fn, lambda msg: (self.ctx.toast(msg, "ok"), self.run()))

    def _defender(self) -> None:
        import sys
        from ..paths import DATA_DIR, IS_FROZEN
        paths = [str(DATA_DIR)]
        if IS_FROZEN:
            paths.append(sys.executable)
        if not ConfirmDialog.ask(self, "Исключения Защитника",
                                 "Добавить в исключения Защитника Windows:\n\n" + "\n".join(paths) +
                                 "\n\nWinDivert и winws.exe — не вирусы, но антивирусы часто помечают их как "
                                 "«HackTool» и удаляют, из-за чего обход перестаёт работать.", "Добавить"):
            return
        run_bg(lambda: winutils.defender_add_exclusions(paths), lambda r: self.ctx.toast(r[1], "ok" if r[0] else "err", 9000))

    def _repair(self) -> None:
        def work():
            ok = self.ctx.zapret.repair_files()
            return ok, "Файлы zapret восстановлены" if ok else "Не все файлы удалось восстановить — проверьте антивирус"
        run_bg(work, lambda r: self.ctx.toast(r[1], "ok" if r[0] else "err"))

    def _discord(self) -> None:
        if not ConfirmDialog.ask(self, "Кэш Discord", "Закрыть Discord и очистить его кэш?", "Очистить"):
            return
        run_bg(diagnostics.clear_discord_cache, lambda lines: self.ctx.toast("\n".join(lines), "ok", 7000))

    def _net_reset(self) -> None:
        if not ConfirmDialog.ask(self, "Сброс сети",
                                 "Будут выполнены команды:\n\nnetsh winsock reset\nnetsh int ip reset all\n"
                                 "netsh winhttp reset proxy\nipconfig /flushdns\n\nПосле этого нужно перезагрузить компьютер. "
                "Продолжить?", "Сбросить", danger=True):
            return

        def work():
            for cmd in (["netsh", "winsock", "reset"], ["netsh", "int", "ip", "reset", "all"],
                        ["netsh", "winhttp", "reset", "proxy"], ["ipconfig", "/flushdns"]):
                winutils.run(cmd, timeout=60)
            return True, "Сеть сброшена. Перезагрузите компьютер."
        run_bg(work, lambda r: self.ctx.toast(r[1], "ok", 8000))


class SettingsPage(Page):
    title = "Настройки"
    subtitle = "Запуск, поведение и внешний вид приложения"

    def __init__(self, ctx):
        super().__init__(ctx)
        cfg = ctx.cfg
        c = Card(spacing=8)
        c.lay.addWidget(label("Запуск", "sectionTitle"))
        self.autostart = ToggleSwitch()
        self.autostart.clicked.connect(lambda on: ctx.window.set_autostart(on))
        c.lay.addWidget(setting_row("Запускать вместе с Windows",
                                    "Через планировщик заданий с правами администратора — без запроса UAC "
                                    "при каждом входе", self.autostart))
        self.minimized = self._sw("app", "start_minimized")
        c.lay.addWidget(setting_row("При автозапуске сворачивать в трей", "", self.minimized))
        self.z_on = self._sw("zapret", "enabled_on_start")
        c.lay.addWidget(setting_row("Включать zapret при запуске", "В режиме службы Windows не используется", self.z_on))
        self.t_on = self._sw("tg", "enabled_on_start")
        c.lay.addWidget(setting_row("Включать Telegram прокси при запуске", "", self.t_on))
        self.body.addWidget(c)

        c = Card(spacing=8)
        c.lay.addWidget(label("Поведение и вид", "sectionTitle"))
        self.tray = self._sw("app", "close_to_tray")
        c.lay.addWidget(setting_row("Закрытие окна сворачивает в трей",
                                    "Обход и прокси продолжают работать. Выход — через меню значка в трее.",
                                    self.tray))
        self.notif = self._sw("app", "notifications")
        c.lay.addWidget(setting_row("Уведомления", "Сообщать о сбоях и обновлениях", self.notif))
        self.theme = Segmented([("dark", "Тёмная"), ("light", "Светлая")])
        self.theme.set_value(cfg.get("app", "theme", "dark"))
        self.theme.changed.connect(ctx.window.set_theme)
        c.lay.addWidget(setting_row("Тема", "", self.theme))
        self.glass = ToggleSwitch()
        self.glass.setChecked(bool(cfg.get("app", "translucent", True)))
        self.glass.clicked.connect(ctx.window.set_translucent)
        c.lay.addWidget(setting_row("Полупрозрачное окно",
                                    "Размытие фона за окном (Windows 10/11). Выключите, если окно выглядит "
                                    "некорректно или видеокарта слабая.", self.glass))
        self.body.addWidget(c)

        c = Card(spacing=8)
        c.lay.addWidget(label("О программе", "sectionTitle"))
        from ..tgproxy import TGWS_VERSION
        c.lay.addWidget(label(
            f"ZapretTG {APP_VERSION}\n"
            f"zapret-discord-youtube {ctx.zapret.local_version()}  ·  tg-ws-proxy {TGWS_VERSION}\n"
            f"Данные: {DATA_DIR}", "hint", selectable=True))
        c.lay.addWidget(label("Объединяет две утилиты с открытым исходным кодом, их функции и стратегии не изменены:",
                              "hint", wrap=True))
        c.lay.addLayout(row(
            button("Flowseal/zapret-discord-youtube", "link", "",
                   lambda: winutils.open_url("https://github.com/Flowseal/zapret-discord-youtube")),
            button("bol-van/zapret", "link", "", lambda: winutils.open_url("https://github.com/bol-van/zapret")),
            button("Flowseal/tg-ws-proxy", "link", "", lambda: winutils.open_url("https://github.com/Flowseal/tg-ws-proxy")),
            None))
        c.lay.addLayout(row(button("Открыть папку данных", "", "folder", lambda: winutils.open_path(str(DATA_DIR))),
                            None))
        self.body.addWidget(c)
        self.finish()

    def _sw(self, section: str, key: str) -> ToggleSwitch:
        sw = ToggleSwitch()
        sw.setChecked(bool(self.ctx.cfg.get(section, key)))
        sw.clicked.connect(lambda on: self.ctx.cfg.set(section, key, on))
        return sw

    def on_show(self) -> None:
        self.autostart.setChecked(bool(self.ctx.cfg.get("app", "autostart")))


class LogsPage(Page):
    title = "Логи"
    subtitle = "Вывод winws.exe, Telegram прокси и самого приложения"

    def __init__(self, ctx):
        super().__init__(ctx, scroll=False)
        self.tabs = QTabWidget()
        self.views = {}
        for key, title in (("zapret", "Zapret"), ("tg", "Telegram прокси"), ("app", "Приложение")):
            v = QPlainTextEdit()
            v.setObjectName("mono")
            v.setReadOnly(True)
            v.setLineWrapMode(QPlainTextEdit.NoWrap)
            v.setMaximumBlockCount(3000)
            self.views[key] = v
            self.tabs.addTab(v, title)
        self.body.addWidget(self.tabs, 1)
        self.body.addLayout(row(button("Открыть папку логов", "", "folder", lambda: winutils.open_path(str(LOG_DIR))),
                                button("Копировать", "", "copy", self._copy), None))
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)
        self._last = {}

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.tabs.currentWidget().toPlainText())
        self.ctx.toast("Скопировано", "ok")

    @staticmethod
    def _tail(path, n=600) -> str:
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 200_000))
                data = f.read().decode("utf-8", errors="replace")
            return "\n".join(data.splitlines()[-n:])
        except Exception:
            return ""

    def refresh(self) -> None:
        z = "\n".join(self.ctx.zapret.output) or self._tail(ZAPRET_LOG) or "winws.exe пока ничего не вывел"
        texts = {"zapret": z, "tg": self._tail(PROXY_LOG) or "Лог пуст", "app": self._tail(APP_LOG) or "Лог пуст"}
        for k, txt in texts.items():
            if self._last.get(k) != txt:
                v = self.views[k]
                bar = v.verticalScrollBar()
                at_end = bar.value() >= bar.maximum() - 4
                v.setPlainText(txt)
                if at_end:
                    bar.setValue(bar.maximum())
                self._last[k] = txt

    def on_show(self) -> None:
        self.refresh()
        self.timer.start()

    def on_hide(self) -> None:
        self.timer.stop()
