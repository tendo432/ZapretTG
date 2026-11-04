"""Вкладка Zapret — всё, что умеет service.bat."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import winutils
from .base import Page
from .fancy import Combo, ConfirmDialog
from .widgets import Card, Pill, Segmented, ToggleSwitch, button, hline, label, row, run_bg, setting_row


class ZapretPage(Page):
    title = "Zapret"
    subtitle = "Стратегии, служба Windows, фильтры, списки доменов и обслуживание"

    def __init__(self, ctx):
        super().__init__(ctx)
        z = ctx.zapret

        # ---------------- стратегия и режим
        c = Card()
        c.lay.addWidget(label("Стратегия и режим запуска", "sectionTitle"))
        self.combo = Combo()
        self.combo.activated.connect(self._strategy_changed)
        self.note = label("", "hint", wrap=True)
        c.lay.addLayout(row(label("Стратегия"), self.combo, None))
        c.lay.addWidget(self.note)
        c.lay.addWidget(label("Если сайты не открываются — попробуйте другую стратегию (ALT, FAKE и т.д.) "
                              "или запустите «Тест стратегий», чтобы найти рабочую.", "hint", wrap=True))
        c.lay.addWidget(hline())
        self.mode = Segmented([("app", "Через приложение"), ("service", "Служба Windows")])
        self.mode.changed.connect(self._mode_changed)
        c.lay.addWidget(setting_row(
            "Режим запуска",
            "«Через приложение» — обход работает, пока запущено приложение (рекомендуется). "
            "«Служба Windows» — как Install Service в service.bat: работает даже без приложения.",
            self.mode))
        self.svc_line = label("", "hint", wrap=True)
        self.svc_pill = Pill("", "off")
        c.lay.addLayout(row(self.svc_pill, self.svc_line, None))
        self.svc_buttons = row(
            button("Установить службу", "", "download", self._install_service),
            button("Запустить", "", "play", lambda: self._bg(z.service_start)),
            button("Остановить", "", "power", lambda: self._bg(z.service_stop)),
            button("Удалить службы", "danger", "trash", self._remove_services,
                   tip="Удалить службы zapret и WinDivert (Remove Services)"),
            None)
        c.lay.addLayout(self.svc_buttons)
        self.auto_restart = ToggleSwitch()
        self.auto_restart.clicked.connect(lambda on: ctx.cfg.set("zapret", "auto_restart", on))
        c.lay.addWidget(setting_row("Перезапускать при сбое",
                                    "Если winws.exe неожиданно завершится, приложение запустит его снова",
                                    self.auto_restart))
        self.body.addWidget(c)

        # ---------------- Game filter / IPSet
        c = Card()
        c.lay.addWidget(label("Фильтры", "sectionTitle"))
        self.gf = Segmented([("disabled", "Выкл"), ("all", "TCP и UDP"), ("tcp", "TCP"), ("udp", "UDP")])
        c.lay.addWidget(setting_row("Game Filter",
                                    "Обход для игр и сервисов на портах выше 1023. Если игра или программа "
                                    "перестала работать с zapret — выключите.", self.gf))
        self.gf_tcp = QLineEdit()
        self.gf_udp = QLineEdit()
        for e in (self.gf_tcp, self.gf_udp):
            e.setPlaceholderText("1024-65535")
            e.setMaximumWidth(220)
        self.gf_save = button("Сохранить", "primary", "", self._save_gf)
        c.lay.addLayout(row(label("Порты TCP"), self.gf_tcp, 12, label("Порты UDP"), self.gf_udp, 12,
                            self.gf_save, None))
        c.lay.addWidget(label("Пример: 1024-1934,1936-65535", "faint"))
        self.gf.changed.connect(lambda _k: self._save_gf())
        c.lay.addWidget(hline())
        self.ipset = Segmented([("none", "Выкл (none)"), ("loaded", "По списку (loaded)"), ("any", "Любой IP (any)")])
        self.ipset.changed.connect(self._ipset_changed)
        c.lay.addWidget(setting_row("IPSet Filter",
                                    "Обход сервисов по IP из ipset-all.txt. «Любой IP» — под фильтр попадает "
                                    "любой адрес. Если что-то перестало открываться — поставьте «Выкл».",
                                    self.ipset))
        c.lay.addLayout(row(button("Обновить список IPSet", "", "refresh", self._update_ipset), None))
        self.body.addWidget(c)

        # ---------------- списки
        c = Card()
        c.lay.addWidget(label("Свои списки", "sectionTitle"))
        c.lay.addWidget(label("По одному домену или IP на строку. Изменения применяются после перезапуска обхода.",
                              "hint", wrap=True))
        self.tabs = QTabWidget()
        self.editors = {}
        for fname, title in z.USER_LISTS.items():
            ed = QPlainTextEdit()
            ed.setObjectName("mono")
            ed.setMinimumHeight(150)
            self.editors[fname] = ed
            self.tabs.addTab(ed, title)
        c.lay.addWidget(self.tabs)
        c.lay.addLayout(row(button("Сохранить и перезапустить", "primary", "check", self._save_lists),
                            button("Открыть папку lists", "", "folder", lambda: winutils.open_path(str(z.lists_dir))),
                            None))
        self.body.addWidget(c)

        # ---------------- фейки
        c = Card()
        c.lay.addWidget(label("Активные фейки", "sectionTitle"))
        c.lay.addWidget(label("Замена фейковых пакетов, которые используются для Discord UDP и Game Filter UDP "
                              "(Replace active fakes).", "hint", wrap=True))
        self.fake_discord = Combo(min_chars=30)
        self.fake_game = Combo(min_chars=30)
        c.lay.addLayout(row(label("Discord UDP"), self.fake_discord,
                            button("Заменить", "", "", lambda: self._replace_fake("discord")), None))
        c.lay.addLayout(row(label("GameFilter UDP"), self.fake_game,
                            button("Заменить", "", "", lambda: self._replace_fake("game")), None))
        self.body.addWidget(c)

        # ---------------- обслуживание
        c = Card()
        c.lay.addWidget(label("Обслуживание", "sectionTitle"))
        self.ver = label("", "hint")
        c.lay.addWidget(self.ver)
        c.lay.addLayout(row(
            button("Проверить обновления", "", "refresh", self._check_update),
            button("Обновить zapret", "", "download", self._do_update,
                   tip="Скачать последний релиз с GitHub и установить, сохранив ваши списки и настройки"),
            button("Тест стратегий", "", "flask", self._tests),
            None))
        c.lay.addLayout(row(
            button("Обновить hosts", "", "globe", self._hosts,
                   tip="Для веб-версии Telegram и голосовых каналов Discord"),
            button("Убрать записи из hosts", "", "trash", lambda: self._bg(z.hosts_remove)),
            button("Открыть папку zapret", "", "folder", lambda: winutils.open_path(str(z.root))),
            None))
        self.upd_switch = ToggleSwitch()
        self.upd_switch.clicked.connect(self._toggle_upd)
        c.lay.addWidget(setting_row("Проверять обновления zapret при запуске", "", self.upd_switch))
        self.body.addWidget(c)
        self.finish()
        self.reload()

    # ------------------------------------------------------------------
    def _bg(self, fn, after=None):
        def done(res):
            if isinstance(res, tuple) and len(res) >= 2:
                ok, msg = res[0], res[1]
                if msg:
                    self.ctx.toast(str(msg), "ok" if ok else "err")
            if after:
                after()
            self.ctx.refresh_now()
        run_bg(fn, done, lambda e: self.ctx.toast(f"Ошибка: {e}", "err"))

    def reload(self) -> None:
        z, cfg = self.ctx.zapret, self.ctx.cfg
        cur = cfg.get("zapret", "strategy")
        self.combo.clear()
        for s in z.strategies():
            self.combo.addItem(z.strategy_title(s), s)
        self.combo.setCurrentIndex(max(self.combo.findData(cur), 0))
        self._note()
        self.mode.set_value(cfg.get("zapret", "mode", "app"))
        self.auto_restart.setChecked(bool(cfg.get("zapret", "auto_restart", True)))
        gf = z.game_filter()
        self.gf.set_value(gf["mode"])
        self.gf_tcp.setText(gf["tcp"])
        self.gf_udp.setText(gf["udp"])
        self.ipset.set_value(z.ipset_status())
        for fname, ed in self.editors.items():
            ed.setPlainText(z.read_list(fname).replace("\r\n", "\n").rstrip("\n"))
        f = z.fakes()
        for combo, key in ((self.fake_discord, "discord"), (self.fake_game, "game")):
            combo.clear()
            combo.addItems(f["files"])
            i = combo.findText(f[key])
            if i >= 0:
                combo.setCurrentIndex(i)
            else:
                combo.insertItem(0, f[key])
                combo.setCurrentIndex(0)
        self.ver.setText(f"Версия zapret: {z.local_version()}  ·  папка: {z.root}")
        self.upd_switch.setChecked(bool(cfg.get("zapret", "check_updates", True)))

    def _note(self) -> None:
        s = self.combo.currentData()
        n = self.ctx.zapret.strategy_note(s) if s else ""
        self.note.setText(("⚠ " + n) if n else "")
        self.note.setVisible(bool(n))

    def _strategy_changed(self, _i) -> None:
        self._note()
        s = self.combo.currentData()
        if self.ctx.cfg.get("zapret", "mode") == "service" and self.ctx.zapret.service_installed():
            self.ctx.cfg.set("zapret", "strategy", s)
            self.ctx.toast("Нажмите «Установить службу», чтобы служба использовала новую стратегию", "info")
            return
        self.ctx.apply_strategy(s)

    def _mode_changed(self, mode: str) -> None:
        z = self.ctx.zapret
        if mode == "service":
            if not z.service_installed():
                self._install_service()
            else:
                self.ctx.cfg.set("zapret", "mode", "service")
        else:
            if z.service_installed():
                if not ConfirmDialog.ask(self, "Режим запуска",
                                         "Удалить службу zapret и запускать обход через приложение?", "Удалить службу"):
                    self.mode.set_value("service")
                    return
                def work():
                    z.remove_services()
                    return z.start()
                self._bg(work)
            self.ctx.cfg.set("zapret", "mode", "app")

    def _install_service(self) -> None:
        s = self.combo.currentData()
        self.ctx.toast(f"Установка службы со стратегией {self.ctx.zapret.strategy_title(s)}…", "info")
        self._bg(lambda: self.ctx.zapret.install_service(s), lambda: self.mode.set_value(self.ctx.cfg.get("zapret", "mode")))

    def _remove_services(self) -> None:
        if not ConfirmDialog.ask(self, "Удалить службы", "Остановить и удалить службы zapret и WinDivert?", "Удалить", danger=True):
            return
        self._bg(self.ctx.zapret.remove_services, lambda: self.mode.set_value("app"))

    def _save_gf(self) -> None:
        z = self.ctx.zapret
        tcp, udp = self.gf_tcp.text().strip() or "1024-65535", self.gf_udp.text().strip() or "1024-65535"
        if not z.validate_range(tcp) or not z.validate_range(udp):
            self.ctx.toast("Неверный формат портов. Пример: 1024-1934,1936-65535", "err")
            return
        z.set_game_filter(self.gf.value() or "disabled", tcp, udp)
        self.ctx.restart_zapret_if_running("Game Filter сохранён")

    def _ipset_changed(self, mode: str) -> None:
        ok, msg = self.ctx.zapret.set_ipset_mode(mode)
        if not ok:
            self.ctx.toast(msg, "err")
            self.ipset.set_value(self.ctx.zapret.ipset_status())
            return
        self.ctx.restart_zapret_if_running(f"IPSet: {mode}")

    def _update_ipset(self) -> None:
        self.ctx.toast("Загрузка списка IPSet…", "info")
        self._bg(self.ctx.zapret.update_ipset, lambda: (self.ipset.set_value(self.ctx.zapret.ipset_status()),
                                                         self.ctx.restart_zapret_if_running(None)))

    def _save_lists(self) -> None:
        for fname, ed in self.editors.items():
            self.ctx.zapret.write_list(fname, ed.toPlainText())
        self.ctx.restart_zapret_if_running("Списки сохранены")

    def _replace_fake(self, kind: str) -> None:
        combo = self.fake_discord if kind == "discord" else self.fake_game
        ok, msg = self.ctx.zapret.replace_fake(kind, combo.currentText())
        if ok:
            self.ctx.restart_zapret_if_running("Активный фейк заменён")
        else:
            self.ctx.toast(msg, "err")

    def _check_update(self) -> None:
        def done(res):
            latest, msg = res
            self.ctx.toast(msg, "warn" if latest else "ok")
        run_bg(self.ctx.zapret.check_update, done)

    def _do_update(self) -> None:
        if not ConfirmDialog.ask(self, "Обновить zapret",
                                 "Скачать последнюю версию zapret с GitHub и установить её? "
                                 "Ваши списки, Game Filter и режим IPSet сохранятся.", "Обновить"):
            return
        self.ctx.toast("Обновление zapret…", "info")
        self._bg(self.ctx.zapret.download_update, lambda: (self.reload(), self.ctx.reload_strategies()))

    def _tests(self) -> None:
        ok, msg = self.ctx.zapret.run_tests()
        self.ctx.toast(msg, "ok" if ok else "err")
        self.ctx.refresh_now()

    def _hosts(self) -> None:
        def done(res):
            ok, msg, remote = res
            if ok is None:
                self.ctx.toast(msg, "err")
            elif ok:
                self.ctx.toast(msg, "ok")
            else:
                dlg = HostsDialog(self, remote)
                if dlg.exec() == QDialog.Accepted:
                    self._bg(lambda: self.ctx.zapret.hosts_apply(remote))
        self.ctx.toast("Проверка hosts…", "info")
        run_bg(self.ctx.zapret.hosts_check, done)

    def _toggle_upd(self, on: bool) -> None:
        self.ctx.cfg.set("zapret", "check_updates", on)
        flag = self.ctx.zapret.utils_dir / "check_updates.enabled"
        try:
            if on:
                flag.write_text("ENABLED\r\n")
            elif flag.exists():
                flag.unlink()
        except OSError:
            pass

    def on_status(self, zs: dict, ts: dict, ds: dict = None) -> None:
        svc = zs.get("service")
        if svc:
            strat = zs.get("service_strategy") or "?"
            self.svc_pill.set("служба: " + {"running": "работает", "stopped": "остановлена"}.get(svc, svc),
                              "on" if svc == "running" else "warn")
            self.svc_line.setText(f"стратегия службы: {strat}  ·  WinDivert: {zs.get('windivert') or 'нет'}")
        else:
            self.svc_pill.set("служба не установлена", "off")
            self.svc_line.setText(f"WinDivert: {zs.get('windivert') or 'не загружен'}")

    def on_show(self) -> None:
        self.reload()


def HostsDialog(parent, remote: str):
    ed = QPlainTextEdit(remote)
    ed.setObjectName("mono")
    ed.setReadOnly(True)
    ed.setMinimumHeight(240)
    return ConfirmDialog(parent, "Обновление hosts",
                         "Эти записи нужны для веб-версии Telegram и голосовых каналов Discord. Приложение добавит "
                         "их отдельным блоком (его можно убрать одной кнопкой) и сохранит резервную копию hosts.",
                         ok="Применить", extra=ed)
