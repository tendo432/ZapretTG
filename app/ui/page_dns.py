"""Вкладка DNS — доступ к нейросетям."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout

from .. import winutils
from ..dns import PROVIDERS
from . import icons
from .base import Page
from .widgets import Card, Palette, Pill, Segmented, ToggleSwitch, button, label, row, run_bg, setting_row


class Tile(QFrame):
    def __init__(self, key: str, title: str, desc: str, on_click):
        super().__init__()
        self.key = key
        self.setObjectName("tile")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(3)
        self.t = label(title, "cardTitle")
        lay.addWidget(self.t)
        d = label(desc, "hint", wrap=True)
        lay.addWidget(d)
        self._cb = on_click

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._cb(self.key)


class DnsPage(Page):
    title = "DNS для нейросетей"
    subtitle = "ChatGPT, Claude, Gemini, Copilot, Grok и другие сервисы, закрытые для России"

    def __init__(self, ctx):
        super().__init__(ctx)
        # -------- главный переключатель
        c = Card(padding=20)
        top = QHBoxLayout()
        top.setSpacing(14)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.state_title = label("DNS выключен", "heroTitle")
        self.state_sub = label("", "muted", wrap=True)
        col.addWidget(self.state_title)
        col.addWidget(self.state_sub)
        top.addLayout(col, 1)
        self.switch = ToggleSwitch(big=True)
        self.switch.clicked.connect(lambda on: ctx.set_dns(on))
        top.addWidget(self.switch, 0, Qt.AlignVCenter)
        c.lay.addLayout(top)
        c.lay.addWidget(label(
            "Специальный DNS отдаёт для нейросетей адреса своих прокси, поэтому сервисы перестают видеть, "
            "что вы из России. Остальной трафик идёт как обычно. Прежние настройки DNS сохраняются и "
            "возвращаются при выключении.", "hint", wrap=True))
        self.body.addWidget(c)

        # -------- провайдер
        c = Card()
        c.lay.addWidget(label("Сервис", "sectionTitle"))
        grid = QGridLayout()
        grid.setSpacing(10)
        self.tiles = {}
        items = list(PROVIDERS.items()) + [("custom", {"name": "Свой DNS", "desc": "Укажите адреса вручную"})]
        for i, (key, prov) in enumerate(items):
            t = Tile(key, prov["name"], prov["desc"], self._pick)
            self.tiles[key] = t
            grid.addWidget(t, i // 3, i % 3)
        c.lay.addLayout(grid)
        self.custom = QFrame()
        cl = QGridLayout(self.custom)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setHorizontalSpacing(10)
        self.c_v4 = QLineEdit()
        self.c_v4.setPlaceholderText("1.2.3.4, 5.6.7.8")
        self.c_v6 = QLineEdit()
        self.c_v6.setPlaceholderText("необязательно")
        self.c_doh = QLineEdit()
        self.c_doh.setPlaceholderText("https://example.com/dns-query (нужно для шифрования)")
        cl.addWidget(label("IPv4"), 0, 0)
        cl.addWidget(self.c_v4, 0, 1)
        cl.addWidget(label("IPv6"), 0, 2)
        cl.addWidget(self.c_v6, 0, 3)
        cl.addWidget(label("DoH"), 1, 0)
        cl.addWidget(self.c_doh, 1, 1, 1, 3)
        cl.addWidget(button("Сохранить", "primary", "", self._save_custom), 1, 4)
        c.lay.addWidget(self.custom)
        self.site = button("Сайт сервиса", "link", "", self._open_site)
        c.lay.addLayout(row(label("Адреса сервисов иногда меняются — актуальные смотрите на их сайтах.", "tiny"),
                            None, self.site))
        self.body.addWidget(c)

        # -------- режим
        c = Card()
        c.lay.addWidget(label("Режим", "sectionTitle"))
        self.mode = Segmented([("auto", "Авто"), ("system", "Системный"), ("local", "Через приложение")])
        self.mode.changed.connect(self._mode)
        c.lay.addWidget(setting_row(
            "Как подключать DNS",
            "«Системный» — адреса прописываются в сетевой адаптер; на Windows 11 запросы сразу шифруются (DoH) "
            "и продолжают работать без приложения. «Через приложение» — приложение само шифрует запросы: "
            "для Windows 10 и провайдеров, которые подменяют DNS. «Авто» выбирает сам.",
            self.mode))
        self.mode_info = label("", "hint", wrap=True)
        c.lay.addWidget(self.mode_info)
        self.body.addWidget(c)

        # -------- проверка
        c = Card()
        c.lay.addLayout(row(label("Проверка доступа", "sectionTitle"), None,
                            button("Проверить", "primary", "pulse", self._check)))
        c.lay.addWidget(label("Показывает, из какой страны вас видит сервис. Если не RU — доступ есть.",
                              "hint", wrap=True))
        self.checks = QVBoxLayout()
        self.checks.setSpacing(6)
        c.lay.addLayout(self.checks)
        c.lay.addWidget(label("Если в браузере включён свой «Безопасный DNS» (Chrome, Edge, Firefox, Яндекс), "
                              "он обходит системный — выключите его или выберите «Использовать текущего "
                              "поставщика». После включения перезапустите браузер.", "tiny", wrap=True))
        self.body.addWidget(c)
        self.finish()
        self.on_show()

    # ------------------------------------------------------------------
    def _pick(self, key: str) -> None:
        self.ctx.cfg.set("dns", "provider", key)
        self._refresh_tiles()
        if self.ctx.cfg.get("dns", "enabled") and key != "custom":
            self.ctx.set_dns(True, key)
        elif key != "custom":
            self.ctx.toast(f"Выбран {PROVIDERS[key]['name']}. Включите DNS переключателем сверху.", "info", 3000)

    def _save_custom(self) -> None:
        self.ctx.cfg.update_section("dns", {"custom_v4": self.c_v4.text(), "custom_v6": self.c_v6.text(),
                                            "custom_doh": self.c_doh.text(), "provider": "custom"})
        if self.ctx.cfg.get("dns", "enabled"):
            self.ctx.set_dns(True, "custom")
        else:
            self.ctx.toast("Сохранено", "ok")

    def _mode(self, key: str) -> None:
        self.ctx.cfg.set("dns", "mode", key)
        self._mode_text()
        if self.ctx.cfg.get("dns", "enabled"):
            def work():
                self.ctx.dns.disable()
                return self.ctx.dns.enable()
            run_bg(work, lambda r: (self.ctx.toast(r[1], "ok" if r[0] else "err"), self.ctx.refresh_now()))

    def _mode_text(self) -> None:
        dns = self.ctx.dns
        eff = dns.effective_mode()
        win11 = dns.native_doh()
        txt = {"system": "Системный" + (" (с шифрованием DoH)" if win11 else " (Windows 10: без шифрования)"),
               "local": "Через приложение (DoH на 127.0.0.1)"}[eff]
        self.mode_info.setText(f"Будет использоваться: {txt}")

    def _open_site(self) -> None:
        prov = self.ctx.dns.provider()
        if prov.get("site"):
            winutils.open_url(prov["site"])

    def _refresh_tiles(self) -> None:
        cur = self.ctx.cfg.get("dns", "provider", "xbox")
        for k, t in self.tiles.items():
            t.set_selected(k == cur)
        self.custom.setVisible(cur == "custom")
        self.site.setVisible(bool(self.ctx.dns.provider().get("site")))

    def _check(self) -> None:
        while self.checks.count():
            it = self.checks.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.checks.addWidget(label("Проверка…", "hint"))
        run_bg(self.ctx.dns.check_ai, self._show_checks, lambda e: self.ctx.toast(str(e), "err"))

    def _show_checks(self, res) -> None:
        while self.checks.count():
            it = self.checks.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        p = Palette.p
        for item in res:
            f = QFrame()
            f.setObjectName("diagRow")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(12, 8, 12, 8)
            ic = QLabel()
            ok = item["ok"]
            ic.setPixmap(icons.pixmap("check" if ok else "x", p["on"] if ok else p["err"], 18))
            lay.addWidget(ic)
            lay.addWidget(label(item["title"], "cardTitle"))
            lay.addWidget(label(item["detail"], "hint"), 1)
            lay.addWidget(Pill(item["loc"] or "—", "on" if ok else "err"))
            self.checks.addWidget(f)

    def on_show(self) -> None:
        d = self.ctx.cfg.section("dns")
        self.c_v4.setText(d.get("custom_v4", ""))
        self.c_v6.setText(d.get("custom_v6", ""))
        self.c_doh.setText(d.get("custom_doh", ""))
        self.mode.set_value(d.get("mode", "auto"))
        self._mode_text()
        self._refresh_tiles()
        self.on_status({}, {}, self.ctx.dns.status())

    def on_status(self, zs: dict, ts: dict, ds: dict = None) -> None:
        if not ds:
            return
        on = bool(ds.get("enabled"))
        self.switch.setChecked(on)
        if on:
            self.state_title.setText(f"DNS включён · {ds.get('provider_name')}")
            mode = "через приложение (DoH)" if ds.get("mode") == "local" else "системный"
            extra = f" · запросов: {ds.get('queries')}" if ds.get("mode") == "local" else ""
            self.state_sub.setText(f"Режим: {mode}{extra}")
        else:
            self.state_title.setText("DNS выключен")
            self.state_sub.setText("Используются обычные DNS вашего провайдера")
        if ds.get("error"):
            self.state_sub.setText(self.state_sub.text() + " · " + ds["error"])
