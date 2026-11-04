"""DNS для нейросетей (ChatGPT, Claude, Gemini, Copilot, Grok и др.).

Специальные DNS-сервисы отдают для этих доменов адреса своих прокси,
поэтому сервисы, закрытые для России, начинают открываться.

Два режима:
  * system — DNS прописывается в сетевые адаптеры; на Windows 11 сразу
    регистрируется шаблон DoH, и Windows шифрует запросы сама (провайдер
    не может их подменить). Продолжает работать и без приложения.
  * local  — приложение поднимает свой DNS на 127.0.0.1 и [::1] и
    пересылает запросы по DoH. Для Windows 10 и провайдеров, которые
    перехватывают DNS. Вторым сервером в адаптере остаётся обычный адрес
    сервиса — если приложение закрыть, интернет не пропадёт.

Предыдущие настройки DNS каждого адаптера сохраняются и возвращаются
при выключении.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import socket
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

from . import winutils
from .paths import IS_WINDOWS

log = logging.getLogger("zapret-tg.dns")

PROVIDERS: Dict[str, Dict] = {
    "xbox": {
        "name": "XBox DNS",
        "desc": "ChatGPT и Sora, Gemini и NotebookLM, Claude, GitHub Copilot, DeepL, Notion, Spotify, Xbox, игры",
        "v4": ["111.88.96.50", "111.88.96.51"],
        "v6": ["2a00:ab00:1233:26::50", "2a00:ab00:1233:26::51"],
        "doh": "https://xbox-dns.ru/dns-query",
        "site": "https://xbox-dns.ru",
    },
    "comss": {
        "name": "Comss.one DNS",
        "desc": "ChatGPT, Claude, Microsoft Copilot, GitHub Copilot, Grok и др.",
        "v4": ["212.109.221.20", "212.109.195.93"],
        "v6": [],
        "doh": "https://dns.comss.one/dns-query",
        "site": "https://www.comss.ru/page.php?id=7315",
    },
    "cloudflare": {
        "name": "Cloudflare 1.1.1.1",
        "desc": "Быстрый приватный DNS. Нейросети не разблокирует",
        "v4": ["1.1.1.1", "1.0.0.1"],
        "v6": ["2606:4700:4700::1111", "2606:4700:4700::1001"],
        "doh": "https://cloudflare-dns.com/dns-query",
        "site": "https://1.1.1.1",
    },
    "google": {
        "name": "Google 8.8.8.8",
        "desc": "Публичный DNS Google. Нейросети не разблокирует",
        "v4": ["8.8.8.8", "8.8.4.4"],
        "v6": ["2001:4860:4860::8888", "2001:4860:4860::8844"],
        "doh": "https://dns.google/dns-query",
        "site": "https://developers.google.com/speed/public-dns",
    },
}

# адреса для проверки «откуда сервис нас видит» (Cloudflare /cdn-cgi/trace)
AI_CHECKS = [
    ("ChatGPT", "chatgpt.com"),
    ("Claude", "claude.ai"),
    ("Grok", "grok.com"),
    ("Perplexity", "www.perplexity.ai"),
]

LOCAL_V4 = "127.0.0.1"
LOCAL_V6 = "::1"


# ------------------------------------------------------- мини DNS-кодек

def build_query(name: str, qtype: int = 1) -> bytes:
    tid = random.randint(0, 0xFFFF)
    head = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    q = b"".join(bytes([len(p)]) + p.encode("idna") for p in name.strip(".").split(".")) + b"\x00"
    return head + q + struct.pack(">HH", qtype, 1)


def _skip_name(data: bytes, off: int) -> int:
    while True:
        ln = data[off]
        if ln == 0:
            return off + 1
        if ln & 0xC0 == 0xC0:
            return off + 2
        off += ln + 1


def parse_a(data: bytes) -> List[str]:
    try:
        qd, an = struct.unpack(">HH", data[4:8])
        off = 12
        for _ in range(qd):
            off = _skip_name(data, off) + 4
        res = []
        for _ in range(an):
            off = _skip_name(data, off)
            typ, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[off:off + 10])
            off += 10
            if typ == 1 and rdlen == 4:
                res.append(socket.inet_ntoa(data[off:off + 4]))
            elif typ == 28 and rdlen == 16:
                res.append(socket.inet_ntop(socket.AF_INET6, data[off:off + 16]))
            off += rdlen
        return res
    except Exception:
        return []


def udp_query(server: str, name: str, qtype: int = 1, timeout: float = 3) -> List[str]:
    fam = socket.AF_INET6 if ":" in server else socket.AF_INET
    with socket.socket(fam, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(build_query(name, qtype), (server, 53))
        data, _ = s.recvfrom(4096)
    return parse_a(data)


# --------------------------------------------------- локальный DoH-сервер

class LocalDoH:
    """DNS на 127.0.0.1:53 / [::1]:53, пересылающий запросы по DoH."""

    def __init__(self):
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None
        self.doh_url = ""
        self.fallback: List[str] = []
        self.boot_ips: List[str] = []
        self.host = ""
        self.error = ""
        self.queries = 0
        self.failures = 0
        self._ready = threading.Event()
        self._cache: Dict[bytes, Tuple[float, bytes]] = {}

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self, doh_url: str, fallback: List[str]) -> Tuple[bool, str]:
        self.stop()
        from urllib.parse import urlparse
        self.doh_url = doh_url
        self.host = urlparse(doh_url).hostname or ""
        self.fallback = list(fallback)
        # адрес DoH-сервера узнаём заранее через обычный DNS сервиса,
        # иначе запрос о нём ушёл бы в нас же самих
        ips: List[str] = []
        for srv in fallback:
            try:
                ips = [ip for ip in udp_query(srv, self.host) if ":" not in ip]
                if ips:
                    break
            except Exception:
                continue
        if not ips:
            try:
                ips = list({ai[4][0] for ai in socket.getaddrinfo(self.host, 443, socket.AF_INET)})
            except Exception:
                pass
        if not ips:
            return False, f"Не удалось узнать адрес {self.host}"
        self.boot_ips = ips
        self.error = ""
        self._ready.clear()
        self.thread = threading.Thread(target=self._main, daemon=True, name="local-doh")
        self.thread.start()
        self._ready.wait(5)
        if self.error or not self.running():
            return False, self.error or "Локальный DNS не запустился"
        return True, ""

    def stop(self) -> None:
        if self.loop and self._stop:
            try:
                self.loop.call_soon_threadsafe(self._stop.set)
            except RuntimeError:
                pass
        if self.thread:
            self.thread.join(timeout=5)
        self.thread = None

    def _main(self) -> None:
        loop = asyncio.new_event_loop()
        if IS_WINDOWS:
            # UDP-сервер в asyncio на Windows работает только на Selector-цикле
            loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        self._stop = asyncio.Event()
        try:
            loop.run_until_complete(self._serve())
        except Exception as exc:
            self.error = f"Локальный DNS: {exc}"
            log.error("local DoH: %r", exc)
        finally:
            self._ready.set()
            try:
                loop.close()
            except Exception:
                pass

    async def _serve(self) -> None:
        import httpx
        self.client = httpx.AsyncClient(http2=True, timeout=4.0, verify=_ssl_ctx(), trust_env=False)
        transports = []
        loop = asyncio.get_running_loop()
        bound = 0
        for addr in (LOCAL_V4, LOCAL_V6):
            fam = socket.AF_INET6 if ":" in addr else socket.AF_INET
            try:
                tr, _ = await loop.create_datagram_endpoint(lambda: _UdpProto(self), local_addr=(addr, 53), family=fam)
                transports.append(tr)
                srv = await asyncio.start_server(self._tcp_client, addr, 53, family=fam)
                transports.append(srv)
                bound += 1
            except OSError as exc:
                log.warning("local DoH bind %s: %r", addr, exc)
                if addr == LOCAL_V4:
                    self.error = ("Порт 53 на 127.0.0.1 занят другой программой. "
                                  "Используйте режим «Системный».")
                    self._ready.set()
                    return
        self._ready.set()
        log.info("Локальный DNS запущен (%s → %s)", ", ".join([LOCAL_V4, LOCAL_V6][:bound]), self.doh_url)
        await self._stop.wait()
        for t in transports:
            t.close()
        await self.client.aclose()

    async def resolve(self, query: bytes) -> Optional[bytes]:
        self.queries += 1
        key = query[2:]
        hit = self._cache.get(key)
        now = time.time()
        if hit and hit[0] > now:
            return query[:2] + hit[1][2:]
        from urllib.parse import urlparse
        u = urlparse(self.doh_url)
        for ip in self.boot_ips:
            url = f"https://{ip}{u.path or '/dns-query'}"
            try:
                r = await self.client.post(url, content=query, headers={
                    "content-type": "application/dns-message", "accept": "application/dns-message",
                    "host": self.host}, extensions={"sni_hostname": self.host})
                if r.status_code == 200 and len(r.content) >= 12:
                    data = r.content
                    ttl = _min_ttl(data)
                    if ttl > 0 and len(self._cache) < 4000:
                        self._cache[key] = (now + min(ttl, 300), data)
                    return query[:2] + data[2:]
            except Exception as exc:
                log.debug("DoH %s: %r", ip, exc)
        # запасной путь — обычный DNS сервиса
        self.failures += 1
        for srv in self.fallback:
            try:
                return await loop_udp(srv, query)
            except Exception:
                continue
        return None

    async def _tcp_client(self, reader, writer) -> None:
        try:
            while True:
                hdr = await asyncio.wait_for(reader.readexactly(2), 10)
                (n,) = struct.unpack(">H", hdr)
                q = await reader.readexactly(n)
                resp = await self.resolve(q)
                if resp is None:
                    break
                writer.write(struct.pack(">H", len(resp)) + resp)
                await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass


class _UdpProto(asyncio.DatagramProtocol):
    def __init__(self, srv: LocalDoH):
        self.srv = srv

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        asyncio.ensure_future(self._answer(data, addr))

    async def _answer(self, data, addr):
        resp = await self.srv.resolve(data)
        if resp:
            if len(resp) > 1232:  # не влезает в UDP — флаг TC, клиент повторит по TCP
                q_end = _skip_name(data, 12) + 4
                flags = 0x8000 | 0x0200 | 0x0080 | (0x0100 if data[2] & 0x01 else 0)
                resp = data[:2] + struct.pack(">HHHHH", flags, 1, 0, 0, 0) + data[12:q_end]
            try:
                self.transport.sendto(resp, addr)
            except Exception:
                pass


async def loop_udp(server: str, query: bytes) -> bytes:
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(loop.run_in_executor(None, _udp_raw, server, query), 4)


def _udp_raw(server: str, query: bytes) -> bytes:
    fam = socket.AF_INET6 if ":" in server else socket.AF_INET
    with socket.socket(fam, socket.SOCK_DGRAM) as s:
        s.settimeout(3)
        s.sendto(query, (server, 53))
        return s.recvfrom(65535)[0]


def _min_ttl(data: bytes) -> int:
    try:
        qd, an = struct.unpack(">HH", data[4:8])
        off = 12
        for _ in range(qd):
            off = _skip_name(data, off) + 4
        ttls = []
        for _ in range(an):
            off = _skip_name(data, off)
            _t, _c, ttl, rdlen = struct.unpack(">HHIH", data[off:off + 10])
            ttls.append(ttl)
            off += 10 + rdlen
        return min(ttls) if ttls else 0
    except Exception:
        return 0


def _ssl_ctx():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


# ------------------------------------------------------ менеджер DNS

_PS_ADAPTERS = r"""
$res = @()
Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' } | ForEach-Object {
  $a = $_
  $g = $a.InterfaceGuid
  $p4 = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$g"
  $p6 = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters\Interfaces\$g"
  $s4 = (Get-ItemProperty -Path $p4 -Name NameServer -ErrorAction SilentlyContinue).NameServer
  $s6 = (Get-ItemProperty -Path $p6 -Name NameServer -ErrorAction SilentlyContinue).NameServer
  $cur = (Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue | ForEach-Object { $_.ServerAddresses }) -join ','
  $res += [pscustomobject]@{ index=$a.ifIndex; alias=$a.Name; desc=$a.InterfaceDescription; static4="$s4"; static6="$s6"; current=$cur }
}
ConvertTo-Json -InputObject @($res) -Compress
"""


class DnsManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.local = LocalDoH()
        self._lock = threading.RLock()
        self.last_error = ""

    # ------------------------------------------------------------ конфиг
    def settings(self) -> Dict:
        d = self.cfg.section("dns")
        return d

    def provider(self, key: Optional[str] = None) -> Dict:
        d = self.settings()
        key = key or d.get("provider", "xbox")
        if key == "custom":
            v4 = [x.strip() for x in str(d.get("custom_v4", "")).replace(";", ",").split(",") if x.strip()]
            v6 = [x.strip() for x in str(d.get("custom_v6", "")).replace(";", ",").split(",") if x.strip()]
            return {"name": "Свой DNS", "desc": "", "v4": v4, "v6": v6, "doh": str(d.get("custom_doh", "")).strip(),
                    "site": ""}
        return PROVIDERS.get(key, PROVIDERS["xbox"])

    @staticmethod
    def native_doh() -> bool:
        return winutils.windows_build() >= 22000  # Windows 11

    def effective_mode(self) -> str:
        m = self.settings().get("mode", "auto")
        if m == "auto":
            return "system" if self.native_doh() else "local"
        return m

    # ----------------------------------------------------------- адаптеры
    def adapters(self) -> List[Dict]:
        if not IS_WINDOWS:
            return []
        rc, out = winutils.powershell(_PS_ADAPTERS, timeout=40)
        try:
            data = json.loads(out.strip().splitlines()[-1]) if out.strip() else []
            if isinstance(data, dict):
                data = [data]
            return data
        except Exception:
            log.warning("adapters: %s", out[:300])
            return []

    @staticmethod
    def _set_family(fam: str, index: int, servers: List[str]) -> None:
        name = f"name={index}"
        if not servers:
            winutils.run(["netsh", "interface", fam, "set", "dnsservers", name, "source=static", "address=none",
                          "validate=no"], timeout=20)
            return
        winutils.run(["netsh", "interface", fam, "set", "dnsservers", name, "source=static",
                      f"address={servers[0]}", "register=primary", "validate=no"], timeout=20)
        for i, srv in enumerate(servers[1:], start=2):
            winutils.run(["netsh", "interface", fam, "add", "dnsservers", name, f"address={srv}",
                          f"index={i}", "validate=no"], timeout=20)

    @staticmethod
    def _restore_family(fam: str, index: int, static: str) -> None:
        servers = [s for s in static.replace(" ", ",").split(",") if s.strip()]
        if servers:
            DnsManager._set_family(fam, index, servers)
        else:
            winutils.run(["netsh", "interface", fam, "set", "dnsservers", f"name={index}", "source=dhcp"], timeout=20)

    def _targets(self, prov: Dict, mode: str) -> Tuple[List[str], List[str]]:
        if mode == "local":
            v4 = [LOCAL_V4] + prov["v4"][:1]
            v6 = [LOCAL_V6]
        else:
            v4 = list(prov["v4"])
            v6 = list(prov["v6"])  # пусто → IPv6-DNS провайдера отключаются, иначе запросы ушли бы мимо
        return v4, v6

    # ------------------------------------------------------- вкл / выкл
    def enable(self, provider_key: Optional[str] = None) -> Tuple[bool, str]:
        if not IS_WINDOWS:
            return False, "Только для Windows"
        with self._lock:
            if provider_key:
                self.cfg.set("dns", "provider", provider_key)
            prov = self.provider()
            if not prov["v4"]:
                return False, "Укажите хотя бы один IPv4-адрес DNS"
            mode = self.effective_mode()
            if mode == "local":
                if not prov.get("doh"):
                    return False, "Для режима «Через приложение» нужен адрес DoH"
                ok, msg = self.local.start(prov["doh"], prov["v4"])
                if not ok:
                    return False, msg
            else:
                self.local.stop()
            adapters = self.adapters()
            if not adapters:
                return False, "Не найдено активных сетевых адаптеров"
            saved = self.cfg.get("dns", "saved", {}) or {}
            v4, v6 = self._targets(prov, mode)
            for a in adapters:
                key = str(a["index"])
                if key not in saved:  # сохраняем исходные настройки только один раз
                    saved[key] = {"alias": a.get("alias"), "static4": a.get("static4") or "",
                                  "static6": a.get("static6") or ""}
                self._set_family("ipv4", a["index"], v4)
                self._set_family("ipv6", a["index"], v6)
            self.cfg.set("dns", "saved", saved)
            if mode == "system" and self.native_doh() and prov.get("doh"):
                self._register_doh(prov)
            winutils.run(["ipconfig", "/flushdns"], timeout=15)
            self.cfg.set("dns", "enabled", True)
            self.cfg.set("dns", "applied_mode", mode)
            self.last_error = ""
            enc = "шифрование DoH" if (mode == "local" or (self.native_doh() and prov.get("doh"))) else "без шифрования"
            return True, f"DNS включён: {prov['name']} ({enc})"

    def _register_doh(self, prov: Dict) -> None:
        added = self.cfg.get("dns", "doh_added", []) or []
        cmds = []
        for ip in prov["v4"] + prov["v6"]:
            t = prov["doh"].replace("'", "")
            cmds.append(
                f"if (Get-DnsClientDohServerAddress -ServerAddress '{ip}' -ErrorAction SilentlyContinue) "
                f"{{ Set-DnsClientDohServerAddress -ServerAddress '{ip}' -DohTemplate '{t}' -AllowFallbackToUdp $true -AutoUpgrade $true }} "
                f"else {{ Add-DnsClientDohServerAddress -ServerAddress '{ip}' -DohTemplate '{t}' -AllowFallbackToUdp $true -AutoUpgrade $true; '+{ip}' }}")
        rc, out = winutils.powershell(";".join(cmds), timeout=60)
        for line in out.splitlines():
            if line.startswith("+"):
                added.append(line[1:].strip())
        self.cfg.set("dns", "doh_added", sorted(set(added)))

    def disable(self) -> Tuple[bool, str]:
        if not IS_WINDOWS:
            return False, "Только для Windows"
        with self._lock:
            saved = self.cfg.get("dns", "saved", {}) or {}
            current = {str(a["index"]) for a in self.adapters()}
            for key, s in saved.items():
                if key not in current:
                    continue
                self._restore_family("ipv4", int(key), s.get("static4", ""))
                self._restore_family("ipv6", int(key), s.get("static6", ""))
            added = self.cfg.get("dns", "doh_added", []) or []
            if added:
                winutils.powershell(";".join(
                    f"Remove-DnsClientDohServerAddress -ServerAddress '{ip}' -ErrorAction SilentlyContinue" for ip in added))
            self.local.stop()
            winutils.run(["ipconfig", "/flushdns"], timeout=15)
            # адаптеры, которых сейчас нет, вернём при следующем включении
            self.cfg.set("dns", "saved", {k: v for k, v in saved.items() if k not in current})
            self.cfg.set("dns", "doh_added", [])
            self.cfg.set("dns", "enabled", False)
            return True, "DNS возвращён к прежним настройкам"

    def ensure(self) -> None:
        """Вызывается периодически: поддерживает DNS включённым.

        Подхватывает новые адаптеры (другая Wi-Fi сеть, USB-модем) и
        перезапускает локальный DNS, если он остановился.
        """
        if not IS_WINDOWS or not self.cfg.get("dns", "enabled"):
            return
        with self._lock:
            prov = self.provider()
            mode = self.cfg.get("dns", "applied_mode") or self.effective_mode()
            if mode == "local" and not self.local.running():
                ok, msg = self.local.start(prov["doh"], prov["v4"])
                if not ok:
                    self.last_error = msg
            v4, _v6 = self._targets(prov, mode)
            for a in self.adapters():
                cur = [x for x in (a.get("current") or "").split(",") if x]
                if not cur or cur[0] != v4[0]:
                    log.info("DNS: применяю к адаптеру %s", a.get("alias"))
                    saved = self.cfg.get("dns", "saved", {}) or {}
                    if str(a["index"]) not in saved:
                        saved[str(a["index"])] = {"alias": a.get("alias"), "static4": a.get("static4") or "",
                                                  "static6": a.get("static6") or ""}
                        self.cfg.set("dns", "saved", saved)
                    self.enable()
                    return

    def shutdown(self) -> None:
        """При выходе из приложения: локальный DNS не может работать без нас."""
        if self.cfg.get("dns", "enabled") and (self.cfg.get("dns", "applied_mode") == "local"):
            saved_enabled = True
            self.disable()
            self.cfg.set("dns", "enabled", saved_enabled)  # включим снова при следующем запуске

    def status(self) -> Dict:
        d = self.settings()
        prov = self.provider()
        return {
            "enabled": bool(d.get("enabled")),
            "provider": d.get("provider", "xbox"),
            "provider_name": prov["name"],
            "mode": d.get("applied_mode") or self.effective_mode(),
            "local_running": self.local.running(),
            "queries": self.local.queries,
            "error": self.last_error,
        }

    # --------------------------------------------------------- проверка
    @staticmethod
    def check_ai() -> List[Dict]:
        """Откуда сервисы видят подключение (поле loc в /cdn-cgi/trace)."""
        res = []
        for title, host in AI_CHECKS:
            item = {"title": title, "host": host, "ok": None, "loc": "", "ip": "", "detail": ""}
            try:
                item["ip"] = socket.gethostbyname(host)
            except Exception:
                item["detail"] = "домен не резолвится"
                item["ok"] = False
                res.append(item)
                continue
            try:
                text = winutils.http_get(f"https://{host}/cdn-cgi/trace", timeout=8)
                kv = dict(l.split("=", 1) for l in text.splitlines() if "=" in l)
                item["loc"] = kv.get("loc", "")
                item["ok"] = bool(item["loc"]) and item["loc"] != "RU"
                item["detail"] = f"сервис видит регион: {item['loc'] or '?'}"
            except Exception as exc:
                item["ok"] = False
                item["detail"] = "нет соединения"
                log.debug("check %s: %r", host, exc)
            res.append(item)
        return res
