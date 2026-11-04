"""Вкладка Telegram — все настройки tg-ws-proxy."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLineEdit, QPlainTextEdit, QSpinBox, QWidget

from .. import winutils
from ..paths import PROXY_LOG
from .base import Page
from .widgets import Card, ToggleSwitch, button, hline, label, row, run_bg, setting_row


class TelegramPage(Page):
    title = "Telegram прокси"
    subtitle = "Локальный MTProto-прокси: соединения Telegram Desktop идут через WebSocket и Cloudflare"

    def __init__(self, ctx):
        super().__init__(ctx)
        from ..tgproxy import TGWS_VERSION
        # ---------------- подключение
        c = Card()
        c.lay.addWidget(label("Как подключить", "sectionTitle"))
        c.lay.addWidget(label("1. Включите прокси.  2. Нажмите «Подключить Telegram» — Telegram Desktop "
                              "предложит добавить прокси, нажмите «Включить».  Если Telegram не открылся — "
                              "скопируйте ссылку, отправьте её себе в «Избранное» и нажмите на неё.",
                              "hint", wrap=True))
        self.link = QLineEdit()
        self.link.setReadOnly(True)
        self.link.setObjectName("mono")
        c.lay.addWidget(self.link)
        c.lay.addLayout(row(button("Подключить Telegram", "primary", "link", ctx.open_telegram),
                            button("Копировать ссылку", "", "copy", ctx.copy_link),
                            button("Открыть лог", "", "doc", lambda: winutils.open_path(str(PROXY_LOG))),
                            None))
        self.body.addWidget(c)

        # ---------------- MTProto
        c = Card()
        c.lay.addWidget(label("Подключение MTProto", "sectionTitle"))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self.host = QLineEdit()
        self.host.setToolTip("Адрес, на котором прокси принимает подключения.\n127.0.0.1 — только этот "
                             "компьютер, 0.0.0.0 — все интерфейсы (например, для телефона в той же сети)")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setToolTip("В Telegram Desktop в настройках прокси должен быть указан тот же порт")
        self.secret = QLineEdit()
        self.secret.setObjectName("mono")
        self.secret.setToolTip("Секретный ключ для авторизации клиентов (32 hex-символа)")
        g.addWidget(label("IP-адрес"), 0, 0)
        g.addWidget(self.host, 0, 1)
        g.addWidget(label("Порт"), 0, 2)
        g.addWidget(self.port, 0, 3)
        g.addWidget(label("Ключ"), 1, 0)
        g.addWidget(self.secret, 1, 1, 1, 3)
        g.addWidget(button("Новый ключ", "", "refresh", lambda: self.secret.setText(os.urandom(16).hex())), 1, 4)
        g.setColumnStretch(1, 1)
        c.lay.addLayout(g)
        c.lay.addWidget(hline())
        c.lay.addWidget(label("Датацентры Telegram (DC → IP)", "sectionTitle"))
        c.lay.addWidget(label("По одному правилу на строку, формат: номер:IP, например 4:149.154.167.220", "hint"))
        self.dc = QPlainTextEdit()
        self.dc.setObjectName("mono")
        self.dc.setFixedHeight(90)
        c.lay.addWidget(self.dc)
        self.body.addWidget(c)

        # ---------------- Cloudflare
        c = Card()
        c.lay.addWidget(label("Cloudflare", "sectionTitle"))
        self.cf = ToggleSwitch()
        c.lay.addWidget(setting_row("CF-прокси", "Использовать Cloudflare прокси для недоступных датацентров", self.cf))
        self.h2 = ToggleSwitch()
        c.lay.addWidget(setting_row("Мультиплексирование медиа (HTTP/2)",
                                    "Объединять загрузку медиа через Cloudflare в общее HTTP/2-соединение. "
                                    "Требуется включённый CF-прокси и TLS.", self.h2))
        self.cf_user_on = QCheckBox("Свой домен (вместо автоматического выбора)")
        self.cf_user = QLineEdit()
        self.cf_user.setPlaceholderText("example.com, example2.com")
        c.lay.addWidget(self.cf_user_on)
        c.lay.addLayout(row(self.cf_user, button("Тест", "", "pulse", self._test_cf)))
        c.lay.addWidget(hline())
        self.worker_on = QCheckBox("Cloudflare Worker")
        self.worker = QLineEdit()
        self.worker.setPlaceholderText("name.account.workers.dev")
        c.lay.addWidget(self.worker_on)
        c.lay.addWidget(label("Домены Cloudflare Worker через запятую — прокси передаёт через них подключение "
                              "к Telegram.", "hint", wrap=True))
        c.lay.addLayout(row(self.worker, button("Тест", "", "pulse", self._test_worker)))
        self.test_result = label("", "hint", wrap=True, selectable=True)
        c.lay.addWidget(self.test_result)
        self.body.addWidget(c)

        # ---------------- дополнительно
        c = Card()
        c.lay.addWidget(label("Дополнительно", "sectionTitle"))
        self.no_secure = ToggleSwitch()
        c.lay.addWidget(setting_row("Выключить TLS для CF-прокси и CF-worker",
                                    "Прокси будет использовать порт 80 для CF-подключений", self.no_secure))
        self.ftls = QLineEdit()
        self.ftls.setPlaceholderText("не используется")
        self.ftls.setMaximumWidth(260)
        c.lay.addWidget(setting_row("Fake TLS домен",
                                    "Маскировка под TLS-соединение к указанному домену (ссылка ee…). "
                                    "Обычно не нужно.", self.ftls))
        self.pp = ToggleSwitch()
        c.lay.addWidget(setting_row("PROXY protocol", "Для работы за nginx/haproxy с proxy_protocol on", self.pp))
        self.buf = QSpinBox()
        self.buf.setRange(4, 65536)
        self.buf.setSuffix(" КБ")
        c.lay.addWidget(setting_row("Буфер", "Размер буфера приёма/передачи (по умолчанию 256 КБ)", self.buf))
        self.pool = QSpinBox()
        self.pool.setRange(0, 64)
        c.lay.addWidget(setting_row("Пул WebSocket-сессий",
                                    "Сколько готовых соединений держать для каждого датацентра (по умолчанию 4). "
                                    "0 отключает прямой маршрут DC→IP.", self.pool))
        self.verbose = ToggleSwitch()
        c.lay.addWidget(setting_row("Подробное логирование", "Нужно при поиске неполадок", self.verbose))
        self.logmb = QSpinBox()
        self.logmb.setRange(1, 200)
        self.logmb.setSuffix(" МБ")
        c.lay.addWidget(setting_row("Макс. размер лога", "", self.logmb))
        self.check_upd = ToggleSwitch()
        c.lay.addWidget(setting_row("Проверять обновления tg-ws-proxy",
                                    f"Встроенная версия: {TGWS_VERSION}", self.check_upd))
        c.lay.addLayout(row(button("Проверить сейчас", "", "refresh", self._check_update), None))
        self.body.addWidget(c)

        self.body.addLayout(row(None, button("Сбросить изменения", "", "", self.reload),
                                button("Сохранить и перезапустить", "primary", "check", self._save)))
        self.finish()
        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        c = self.ctx.cfg.section("tg")
        self.host.setText(str(c.get("host")))
        self.port.setValue(int(c.get("port", 1443)))
        self.secret.setText(str(c.get("secret")))
        self.dc.setPlainText("\n".join(c.get("dc_ip", [])))
        self.cf.setChecked(bool(c.get("cfproxy")))
        self.h2.setChecked(bool(c.get("h2")))
        self.cf_user_on.setChecked(bool(c.get("cfproxy_user_domain_enabled")))
        self.cf_user.setText(", ".join(c.get("cfproxy_user_domain", []) or []))
        self.worker_on.setChecked(bool(c.get("cfproxy_worker_enabled")))
        self.worker.setText(", ".join(c.get("cfproxy_worker_domain", []) or []))
        self.no_secure.setChecked(bool(c.get("no_secure")))
        self.ftls.setText(str(c.get("fake_tls_domain", "") or ""))
        self.pp.setChecked(bool(c.get("proxy_protocol")))
        self.buf.setValue(int(c.get("buf_kb", 256)))
        self.pool.setValue(int(c.get("pool_size", 4)))
        self.verbose.setChecked(bool(c.get("verbose")))
        self.logmb.setValue(int(c.get("log_max_mb", 5)))
        self.check_upd.setChecked(bool(c.get("check_updates", True)))
        self.link.setText(self.ctx.tg.link())

    def _collect(self) -> dict:
        from proxy import coerce_domain_list
        return {
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "secret": self.secret.text().strip().lower(),
            "dc_ip": [l.strip() for l in self.dc.toPlainText().splitlines() if l.strip()],
            "cfproxy": self.cf.isChecked(),
            "h2": self.h2.isChecked(),
            "cfproxy_user_domain_enabled": self.cf_user_on.isChecked(),
            "cfproxy_user_domain": coerce_domain_list(self.cf_user.text()),
            "cfproxy_worker_enabled": self.worker_on.isChecked(),
            "cfproxy_worker_domain": coerce_domain_list(self.worker.text()),
            "no_secure": self.no_secure.isChecked(),
            "fake_tls_domain": self.ftls.text().strip(),
            "proxy_protocol": self.pp.isChecked(),
            "buf_kb": self.buf.value(),
            "pool_size": self.pool.value(),
            "verbose": self.verbose.isChecked(),
            "log_max_mb": self.logmb.value(),
            "check_updates": self.check_upd.isChecked(),
        }

    def _save(self) -> None:
        values = self._collect()
        err = self.ctx.tg.validate(values)
        if err:
            self.ctx.toast(err, "err")
            return
        self.ctx.cfg.update_section("tg", values)
        self.link.setText(self.ctx.tg.link())
        if self.ctx.tg.is_running():
            self.ctx.toast("Настройки сохранены, перезапуск прокси…", "info")
            run_bg(self.ctx.tg.restart, lambda r: (self.ctx.toast(r[1], "ok" if r[0] else "err"), self.ctx.refresh_now()))
        else:
            self.ctx.toast("Настройки сохранены", "ok")

    def _test_cf(self) -> None:
        from proxy import coerce_domain_list
        domains = coerce_domain_list(self.cf_user.text()) if self.cf_user_on.isChecked() else []
        secure = not self.no_secure.isChecked()
        self.test_result.setText("Проверка CF-прокси…")
        run_bg(lambda: self.ctx.tg.test_cfproxy(domains, secure), self.test_result.setText,
               lambda e: self.test_result.setText(f"Ошибка теста: {e}"))

    def _test_worker(self) -> None:
        from proxy import coerce_domain_list
        domains = coerce_domain_list(self.worker.text())
        secure = not self.no_secure.isChecked()
        self.test_result.setText("Проверка Cloudflare Worker…")
        run_bg(lambda: self.ctx.tg.test_cfworker(domains, secure), self.test_result.setText,
               lambda e: self.test_result.setText(f"Ошибка теста: {e}"))

    def _check_update(self) -> None:
        def done(res):
            latest, msg = res
            self.ctx.toast(msg, "warn" if latest else "ok")
        run_bg(self.ctx.tg.check_update, done)

    def on_show(self) -> None:
        self.link.setText(self.ctx.tg.link())
