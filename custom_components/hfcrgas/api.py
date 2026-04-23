"""合燃华润燃气 (HFCRGas) API 客户端."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

_LOGGER = logging.getLogger(__name__)

BASE_URL = "http://ehall.hfgas.cn/apliPay"

# 模拟微信浏览器的 User-Agent
WX_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.71(0x18004728) NetType/WIFI Language/zh_CN"
)


class HFCRGasAPIError(Exception):
    """合肥燃气 API 异常."""


class HFCRGasAuthError(HFCRGasAPIError):
    """认证失败."""


class HFCRGasAPI:
    """合燃华润燃气 API 客户端."""

    def __init__(self, huhao: str, phone: str) -> None:
        """初始化."""
        self.huhao = huhao
        self.phone = phone
        self._session: aiohttp.ClientSession | None = None

        # 使用户号+手机号生成稳定的 openId（模拟微信 openId）
        self.open_id = f"ha_{huhao}"

        # 认证信息
        self.encrypted_yhh: str | None = None
        self.resource_identifier: str | None = None
        self.rqb_gh: str | None = None
        self.rqb_id: str | None = None
        self.meter_type: str | None = None
        self.is_wlw: bool = False
        self.user_name: str | None = None
        self.address: str | None = None
        self.khlx: str = "2"

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session."""
        if self._session is None or self._session.closed:
            cookie_jar = aiohttp.CookieJar(unsafe=True)
            connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.DefaultResolver())
            self._session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=cookie_jar,
                headers={
                    "User-Agent": WX_USER_AGENT,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
                    "Origin": BASE_URL.rsplit("/", 1)[0],
                    "Host": "ehall.hfgas.cn",
                    "Referer": f"{BASE_URL}/router/wxIndex",
                },
            )
        return self._session

    async def close(self) -> None:
        """关闭 session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _post(
        self, path: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """发送 POST 请求."""
        session = await self._get_session()
        url = f"{BASE_URL}{path}"

        headers = {
            "Host": "ehall.hfgas.cn",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "http://ehall.hfgas.cn",
            "Referer": f"{BASE_URL}/router/wxIndex",
        }

        # 手动拼接 form data 字符串，与 HAR 中的请求格式一致
        # 注意：HAR 显示值不做 URL 编码（+, /, = 等字符原样发送）
        if data:
            form_str = "&".join(f"{k}={v}" for k, v in data.items()) + "&"
        else:
            form_str = ""

        _LOGGER.info("POST %s data=%s", path, form_str[:200])

        try:
            async with session.post(
                url, data=form_str, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                # 尝试解析 JSON 响应（即使 HTTP 状态非200，服务器也可能返回有用信息）
                try:
                    result = await resp.json(content_type=None)
                except Exception:
                    text = await resp.text()
                    _LOGGER.warning("服务器返回非JSON: status=%s, path=%s, resp=%s",
                                    resp.status, path, text[:200])
                    raise HFCRGasAPIError(f"服务器错误: HTTP {resp.status}")

                status = result.get("status")
                if status != 200:
                    _LOGGER.warning("POST %s 返回非200状态: status=%s, message=%s",
                                    path, status, result.get("message", ""))
                else:
                    _LOGGER.info("POST %s 成功", path)
                return result
        except asyncio.TimeoutError as err:
            raise HFCRGasAPIError(f"请求超时: {path}") from err
        except aiohttp.ClientError as err:
            raise HFCRGasAPIError(f"请求失败: {err}") from err

    async def _init_session(self) -> None:
        """初始化会话 - 访问页面获取 JSESSIONID cookie."""
        session = await self._get_session()
        try:
            async with session.get(
                f"{BASE_URL}/router/wxIndex",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                _LOGGER.info("初始化会话响应状态: %s", resp.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("初始化会话失败: %s", err)

    async def _fetch_page_auth(self, page_path: str) -> str | None:
        """从功能页面获取 auth 值.

        各功能页面的 HTML 中包含 <input type="hidden" id="auth" value="...">,
        其中的 auth 是调用对应 API 所必需的。
        """
        from urllib.parse import quote

        session = await self._get_session()
        try:
            url = f"{BASE_URL}/router/{page_path}"
            if self.encrypted_yhh:
                url += f"?yhh={quote(self.encrypted_yhh, safe='')}"
            _LOGGER.info("访问页面获取auth: %s", url)
            async with session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                html = await resp.text()
                match = re.search(r'id="auth"\s+value="([^"]*)"', html)
                if match:
                    auth_val = match.group(1)
                    _LOGGER.info("从 %s 获取到 auth: %s", page_path, auth_val[:20])
                    return auth_val
                else:
                    _LOGGER.warning("从 %s 未找到 auth, 页面内容前300字符: %s",
                                    page_path, html[:300])
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("访问页面 %s 获取 auth 失败: %s", page_path, err)
        return None

    def _get_headers(self) -> dict[str, str]:
        """获取请求头，与 hfgas 参考实现一致."""
        return {
            "Host": "ehall.hfgas.cn",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "http://ehall.hfgas.cn",
            "User-Agent": WX_USER_AGENT,
            "Connection": "keep-alive",
            "Referer": f"{BASE_URL}/router/wxIndex",
        }

    @staticmethod
    def _aes_encrypt(plaintext: str, key: str, iv: str) -> str:
        """AES-CBC 加密，与前端 CryptoJS.AES.encrypt 一致.

        前端逻辑（base64.js）:
          key = auth.substring(16)
          iv = auth.substring(0, 16)
          getAesString(yhh, key, iv)  →  AES-CBC, PKCS7 padding, 输出 Base64
        """
        key_bytes = key.encode("utf-8")
        iv_bytes = iv.encode("utf-8")
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        padded = pad(plaintext.encode("utf-8"), AES.block_size)
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(encrypted).decode("utf-8")

    async def _fetch_default_huhao(self) -> bool:
        """通过 getWxDefaultHuhao 获取加密 yhh 和 resourceIdentifier.

        返回 True 如果成功获取到凭证。
        """
        data = {"openId": self.open_id}
        result = await self._post("/query/getWxDefaultHuhao", data)

        if result.get("status") != 200:
            _LOGGER.debug("getWxDefaultHuhao 返回非200: %s", result.get("message"))
            return False

        resp_data = result.get("data", {})
        if not isinstance(resp_data, dict) or not resp_data.get("hh"):
            _LOGGER.debug("getWxDefaultHuhao 返回数据异常")
            return False

        hh = resp_data["hh"]
        if hh.get("jmYhh"):
            self.encrypted_yhh = hh["jmYhh"]
        if resp_data.get("resourceIdentifier"):
            self.resource_identifier = resp_data["resourceIdentifier"]
        if resp_data.get("khlx"):
            self.khlx = resp_data["khlx"]
        if hh.get("name"):
            self.user_name = hh["name"]
        if hh.get("address"):
            self.address = hh["address"]

        return bool(self.encrypted_yhh and self.resource_identifier)

    async def _do_bangding(self) -> None:
        """执行绑定操作.

        绑定只需要做一次。如果户号已绑定，服务器返回500，但这是正常的。
        参考 HAR：先访问 huhaobangding 页面获取 auth，再发送 bangding 请求。
        """
        # 先初始化 session 获取 JSESSIONID cookie
        await self._init_session()

        # 从 huhaobangding 页面获取 auth（bangding 需要此 auth）
        bind_auth = await self._fetch_page_auth("huhaobangding")

        bind_data: dict[str, Any] = {
            "userId": "null",
            "khlx": "2",
            "name": "",
            "jmYhh": self.huhao,
            "phone": "null",
            "openId": self.open_id,
            "source": "wx",
            "phoneVerify": self.phone,
        }
        if bind_auth:
            bind_data["auth"] = bind_auth

        result = await self._post("/query/bangding", bind_data)

        if result.get("status") == 200:
            _LOGGER.info("户号绑定成功")
        elif result.get("status") == 500 and "已绑定" in result.get("message", ""):
            _LOGGER.info("户号已绑定，跳过")
        else:
            msg = result.get("message", "绑定失败")
            raise HFCRGasAuthError(f"绑定失败: {msg}")

    async def bind(self) -> bool:
        """绑定户号 - 核心认证流程.

        1. 先尝试 getWxDefaultHuhao（如果之前已绑定，直接获取凭证）
        2. 如果失败，执行 bangding 绑定，再获取凭证
        """
        # 先尝试直接获取凭证（已绑定的情况）
        if await self._fetch_default_huhao():
            _LOGGER.info("通过 getWxDefaultHuhao 获取凭证成功")
            return True

        # 未绑定，需要先绑定
        _LOGGER.info("未找到绑定信息，尝试绑定")
        await self._do_bangding()

        # 绑定后再获取凭证
        if not await self._fetch_default_huhao():
            raise HFCRGasAuthError("绑定后仍无法获取凭证，请检查户号和手机号")

        return True

    async def _ensure_session_valid(self) -> None:
        """确保 session 有效."""
        if not self.encrypted_yhh or not self.resource_identifier:
            await self.bind()

    async def _refresh_credentials(self) -> None:
        """刷新凭证（不重新绑定，只重新获取 yhh 和 resourceIdentifier）."""
        await self._fetch_default_huhao()

    async def _request_with_retry(
        self,
        path: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """带重试的请求."""
        result = await self._post(path, data)

        if result.get("status") == 200:
            return result

        # 可能凭证过期，尝试刷新
        _LOGGER.warning("请求 %s 失败 (status=%s)，尝试刷新凭证",
                        path, result.get("status"))
        try:
            await self._refresh_credentials()
        except Exception:
            pass

        # 刷新后重试
        data = self._update_data_with_session(data)
        result2 = await self._post(path, data)

        if result2.get("status") == 200:
            return result2

        # 如果刷新凭证也失败，尝试完整重新绑定
        _LOGGER.warning("刷新凭证后仍然失败，尝试重新绑定")
        try:
            await self.bind()
            data = self._update_data_with_session(data)
            return await self._post(path, data)
        except HFCRGasAPIError:
            raise HFCRGasAPIError(f"请求 {path} 失败")

    def _update_data_with_session(self, data: dict[str, Any]) -> dict[str, Any]:
        """用最新的 session 信息更新请求数据."""
        updated = dict(data)
        if self.encrypted_yhh:
            updated["yhh"] = self.encrypted_yhh
        if self.resource_identifier:
            updated["resourceIdentifier"] = self.resource_identifier
        if self.rqb_gh and "rqbGh" in updated:
            updated["rqbGh"] = self.rqb_gh
        if self.rqb_id and "rqbId" in updated:
            updated["rqbId"] = self.rqb_id
        return updated

    async def get_user_info(self) -> dict[str, Any]:
        """获取用户信息."""
        await self._ensure_session_valid()

        data = {
            "yhh": self.encrypted_yhh,
            "resourceIdentifier": self.resource_identifier,
        }

        result = await self._request_with_retry("/query/selectUserInfo", data)

        user_data = result.get("data", {})
        if isinstance(user_data, dict):
            self.is_wlw = user_data.get("isWlw") == "1"
            if user_data.get("yqdzHzMc"):
                self.user_name = user_data["yqdzHzMc"]
            if user_data.get("yqdzSm"):
                self.address = user_data["yqdzSm"]
            if user_data.get("khlx"):
                self.khlx = user_data["khlx"]

        return user_data

    async def get_surplus(self) -> dict[str, Any]:
        """获取余额信息."""
        await self._ensure_session_valid()

        data = {
            "yhh": self.encrypted_yhh,
            "resourceIdentifier": self.resource_identifier,
        }

        result = await self._request_with_retry("/query/getSurplus", data)
        return result.get("data", {})

    async def _init_meter_info(self) -> None:
        """初始化表信息（表号、类型等）.

        参考 HAR 分析：getBghByYhh 需要 auth 参数。
        auth 从 meiriqiliang 页面获取。
        如果 getBghByYhh 失败，则从 getBillList 的 custNo 字段获取。
        """
        # 确保会话已初始化（获取 JSESSIONID cookie）
        try:
            await self._init_session()
        except Exception:
            _LOGGER.debug("初始化会话失败，继续尝试")

        # 从 meiriqiliang 页面获取 auth（getBghByYhh 需要）
        page_auth = await self._fetch_page_auth("meiriqiliang")

        # 尝试 getBghByYhh
        # 前端逻辑：getBghByYhh 的 yhh 需要用 auth 进行 AES-CBC 加密
        # key = auth[16:], iv = auth[:16]
        data: dict[str, Any] = {
            "yhh": self.encrypted_yhh,
            "resourceIdentifier": self.resource_identifier,
        }
        if page_auth:
            data["auth"] = page_auth
            # 对 yhh 进行 AES 加密（仅 getBghByYhh 需要）
            aes_key = page_auth[16:]
            aes_iv = page_auth[:16]
            yhh_plain = self.encrypted_yhh or ""
            encrypted_yhh = self._aes_encrypt(yhh_plain, aes_key, aes_iv)
            data["yhh"] = encrypted_yhh
            _LOGGER.info("getBghByYhh: 原始yhh=%s, 加密yhh=%s",
                         yhh_plain[:10], encrypted_yhh[:20])

        try:
            result = await self._post("/query/getBghByYhh", data)
            _LOGGER.info("getBghByYhh响应: status=%s, data=%s",
                         result.get("status"), str(result.get("data"))[:200])
            if result.get("status") == 200 and result.get("data"):
                bgh_list = result["data"]
                if bgh_list and isinstance(bgh_list, list):
                    if not self.rqb_id:
                        self.rqb_id = bgh_list[0].get("rqbId", "")
                    if not self.rqb_gh:
                        self.rqb_gh = bgh_list[0].get("rqbGh", "")
                    _LOGGER.info("getBghByYhh获取到: rqb_gh=%s, rqb_id=%s", self.rqb_gh, self.rqb_id)
        except HFCRGasAPIError as e:
            _LOGGER.debug("getBghByYhh失败: %s", e)

        # 如果 getBghByYhh 没获取到 rqbGh，尝试从账单列表获取 (custNo 字段)
        if not self.rqb_gh:
            try:
                today = datetime.now()
                start_date = today - timedelta(days=365)
                bill_data = {
                    "yhh": self.encrypted_yhh,
                    "bgnDate": start_date.strftime("%Y%m%d"),
                    "endDate": today.strftime("%Y%m%d"),
                    "rqbGh": "",
                    "rqbId": "",
                    "resourceIdentifier": self.resource_identifier,
                }
                result = await self._post("/query/getBillList", bill_data)
                _LOGGER.info("getBillList(获取表号)响应: status=%s", result.get("status"))
                if result.get("status") == 200 and result.get("data"):
                    bills = result["data"].get("list", [])
                    if bills and isinstance(bills, list):
                        cust_no = bills[0].get("custNo", "")
                        if cust_no:
                            self.rqb_gh = cust_no
                            _LOGGER.info("从账单列表获取到表号: %s", self.rqb_gh)
            except HFCRGasAPIError:
                _LOGGER.debug("从账单列表获取表号失败")

        # 获取表类型
        if self.rqb_gh:
            data2: dict[str, Any] = {
                "rqbGh": self.rqb_gh,
                "yhh": self.encrypted_yhh,
                "resourceIdentifier": self.resource_identifier,
            }
            if page_auth:
                data2["auth"] = page_auth

            try:
                result2 = await self._post("/query/getRqbLx", data2)
                if result2.get("status") == 200 and result2.get("data"):
                    self.meter_type = result2["data"]
                    _LOGGER.info("获取到表类型: %s", self.meter_type)
            except HFCRGasAPIError:
                _LOGGER.debug("获取表类型失败")

        _LOGGER.info("表信息初始化完成: rqb_gh=%s, rqb_id=%s, meter_type=%s",
                     self.rqb_gh, self.rqb_id, self.meter_type)

    async def get_daily_usage(self, days: int = 90) -> dict[str, Any]:
        """获取每日用气量数据."""
        await self._ensure_session_valid()

        today = datetime.now()
        start_date = today - timedelta(days=days)

        data: dict[str, Any] = {
            "yhh": self.encrypted_yhh,
            "bgnDate": start_date.strftime("%Y%m%d"),
            "endDate": today.strftime("%Y%m%d"),
            "rqbGh": self.rqb_gh or "",
            "rqbId": self.rqb_id or "",
            "resourceIdentifier": self.resource_identifier,
        }

        _LOGGER.info("getWlwDay请求参数: rqbGh=%s, rqbId=%s",
                     self.rqb_gh, self.rqb_id)

        result = await self._request_with_retry("/query/getWlwDay", data)
        _LOGGER.info("getWlwDay响应status=%s, data keys=%s",
                     result.get("status"),
                     list(result.get("data", {}).keys()) if isinstance(result.get("data"), dict) else "non-dict")
        return result.get("data") or {}

    async def get_bill_list(self, months: int = 12) -> dict[str, Any]:
        """获取账单列表."""
        await self._ensure_session_valid()

        today = datetime.now()
        start_date = today - timedelta(days=months * 30)

        data = {
            "yhh": self.encrypted_yhh,
            "bgnDate": start_date.strftime("%Y%m%d"),
            "endDate": today.strftime("%Y%m%d"),
            "rqbGh": "",
            "rqbId": "",
            "resourceIdentifier": self.resource_identifier,
        }

        result = await self._request_with_retry("/query/getBillList", data)
        _LOGGER.info("账单列表API响应status=%s", result.get("status"))
        return result.get("data") or {}

    async def get_yearly_usage(self) -> float:
        """获取本年度累计用气量."""
        await self._ensure_session_valid()

        data = {
            "yhh": self.encrypted_yhh,
            "resourceIdentifier": self.resource_identifier,
        }

        try:
            result = await self._request_with_retry("/query/getJtLeiji", data)
            if result.get("status") == 200 and result.get("data"):
                return float(result["data"])
        except (HFCRGasAPIError, ValueError, TypeError):
            _LOGGER.debug("获取年度累计用气量失败")

        return 0.0

    async def _safe_call(self, coro):
        """安全调用协程，捕获异常."""
        try:
            return await coro
        except Exception as err:
            _LOGGER.warning("API调用失败: %s", err)
            return None

    async def get_last_payment(self) -> dict[str, Any]:
        """获取最近缴费记录."""
        await self._ensure_session_valid()

        data = {
            "yhh": self.encrypted_yhh,
            "resourceIdentifier": self.resource_identifier,
        }

        try:
            result = await self._request_with_retry("/query/payInfos", data)
            if result.get("status") == 200 and result.get("data"):
                pay_infos = result["data"].get("payInfos", [])
                if pay_infos and isinstance(pay_infos, list):
                    last = pay_infos[0]
                    return {
                        "amount": float(last.get("rcvAmt", 0)),
                        "date": last.get("payDate"),
                    }
        except (HFCRGasAPIError, ValueError, TypeError):
            _LOGGER.debug("获取最近缴费记录失败")

        return {"amount": 0.0, "date": None}

    async def get_all_data(self) -> dict[str, Any]:
        """获取所有燃气数据（供 coordinator 调用）."""
        await self._ensure_session_valid()

        _LOGGER.info("开始获取数据: rqb_gh=%s, rqb_id=%s",
                     self.rqb_gh, self.rqb_id)

        # 初始化会话获取 JSESSIONID Cookie
        try:
            await self._init_session()
        except Exception:
            _LOGGER.debug("初始化会话失败，继续尝试获取数据")

        # 如果关键参数缺失，初始化表信息
        if not self.rqb_gh or not self.rqb_id:
            _LOGGER.info("表信息不完整(rqb_gh=%s, rqb_id=%s)，初始化表信息",
                         self.rqb_gh, self.rqb_id)
            await self._init_meter_info()

        # 并行获取所有数据（与 hfgas 参考实现一致）
        daily_result, bill_result, user_info_result, surplus_result, yearly_result, payment_result = await asyncio.gather(
            self._safe_call(self.get_daily_usage()),
            self._safe_call(self.get_bill_list()),
            self._safe_call(self.get_user_info()),
            self._safe_call(self.get_surplus()),
            self._safe_call(self.get_yearly_usage()),
            self._safe_call(self.get_last_payment()),
            return_exceptions=True,
        )

        # 处理用户信息
        user_info = user_info_result if isinstance(user_info_result, dict) else {}

        # 处理余额
        surplus = surplus_result if isinstance(surplus_result, dict) else {}

        # 处理日用量数据
        daily_data = daily_result if isinstance(daily_result, dict) else {}
        if not daily_result:
            _LOGGER.warning("获取日用量数据失败")

        # 处理账单数据
        bill_data = bill_result if isinstance(bill_result, dict) else {}
        if not bill_result:
            _LOGGER.warning("获取账单数据失败")

        # 处理年度用气量
        yearly_usage = yearly_result if isinstance(yearly_result, (int, float)) else 0.0

        # 处理最近缴费
        last_payment = payment_result if isinstance(payment_result, dict) else {"amount": 0.0, "date": None}

        # 解析日用量数据（燃气第二天更新前一天数据，所以最新一条就是昨日用气量）
        yesterday_usage = 0.0
        meter_reading = 0.0
        monthly_usage = 0.0

        if daily_data and isinstance(daily_data, dict):
            yql = daily_data.get("YQL", [])
            biao_ji_shus = daily_data.get("biaoJiShus", [])
            ri_qi = daily_data.get("riQi", [])

            _LOGGER.info("日用量数据: YQL=%d条, biaoJiShus=%d条, riQi=%d条",
                         len(yql), len(biao_ji_shus), len(ri_qi))

            if yql:
                try:
                    yesterday_usage = float(yql[-1]) if yql[-1] else 0.0
                except (ValueError, IndexError):
                    pass
            if biao_ji_shus:
                try:
                    meter_reading = float(biao_ji_shus[-1])
                except (ValueError, IndexError):
                    pass

            # 按月累计用气量
            if yql and ri_qi:
                try:
                    latest_date_str = ri_qi[-1]
                    latest_date = datetime.strptime(latest_date_str.split()[0], "%Y-%m-%d")
                    current_month = (latest_date.year, latest_date.month)
                    for i, date_str in enumerate(ri_qi):
                        try:
                            d = datetime.strptime(date_str.split()[0], "%Y-%m-%d")
                            if (d.year, d.month) == current_month and i < len(yql):
                                monthly_usage += float(yql[i])
                        except (ValueError, IndexError):
                            continue
                    monthly_usage = round(monthly_usage, 2)
                except (ValueError, IndexError):
                    pass

        # 如果日用量中没有 meter_reading，尝试从 biaoJiShus 获取
        if not meter_reading and daily_data:
            biao_ji_shus = daily_data.get("biaoJiShus", [])
            if biao_ji_shus:
                try:
                    meter_reading = float(biao_ji_shus[-1])
                except (ValueError, IndexError):
                    pass

        # 解析账单数据
        last_bill_amount = 0.0
        last_bill_date = None
        last_bill_ym = None
        current_period_usage = 0.0

        if bill_data and isinstance(bill_data, dict):
            bills = bill_data.get("list", [])
            _LOGGER.info("账单数据: %d条账单", len(bills))
            if bills:
                try:
                    last_bill_amount = float(bills[0].get("totalAmt", 0))
                    last_bill_date = bills[0].get("billDate")
                    last_bill_ym = bills[0].get("billYm")
                    current_period_usage = float(bills[0].get("bcyql", 0))
                except (ValueError, IndexError):
                    pass

        # 解析余额数据 (prepayAmt 单位为分，需除以100得到元)
        balance = 0.0
        if surplus and isinstance(surplus, dict):
            try:
                balance = float(surplus.get("prepayAmt", 0)) / 100
            except (ValueError, TypeError):
                pass

        _LOGGER.info(
            "数据汇总: yesterday=%.2f, monthly=%.2f, yearly=%.2f, "
            "meter_reading=%.2f, balance=%.2f, latest_bill_usage=%.2f",
            yesterday_usage, monthly_usage, yearly_usage,
            meter_reading, balance, current_period_usage
        )

        return {
            "user_info": user_info,
            "surplus": surplus,
            "meter_info": {
                "rqb_gh": self.rqb_gh,
                "meter_type": self.meter_type,
                "rqb_id": self.rqb_id,
            },
            "huhao": self.huhao,
            "user_name": self.user_name,
            "address": self.address,
            "meter_type": self.meter_type,
            "rqb_gh": self.rqb_gh,
            "is_wlw": self.is_wlw,
            "yesterday_usage": yesterday_usage,
            "monthly_usage": monthly_usage,
            "yearly_usage": yearly_usage,
            "meter_reading": meter_reading,
            "last_bill_amount": last_bill_amount,
            "last_bill_date": last_bill_date,
            "last_bill_ym": last_bill_ym,
            "current_period_usage": current_period_usage,
            "balance": balance,
            "last_payment_amount": last_payment.get("amount", 0.0),
            "last_payment_date": last_payment.get("date"),
            "daily_data": daily_data,
            "bill_data": bill_data,
        }


async def validate_input(huhao: str, phone: str) -> HFCRGasAPI:
    """验证用户输入，成功返回 API 实例."""
    if not re.match(r"^\d{10}$", huhao):
        raise HFCRGasAPIError("户号应为10位数字")

    if not re.match(r"^1[3-9]\d{9}$", phone):
        raise HFCRGasAPIError("手机号格式不正确")

    api = HFCRGasAPI(huhao, phone)
    try:
        await api.bind()
        await api.get_user_info()
        # 初始化表信息（获取 rqbGh, rqbId 等）
        try:
            await api._init_meter_info()
        except Exception:
            _LOGGER.debug("初始化表信息失败，但配置仍然保存")
        return api
    except (HFCRGasAuthError, HFCRGasAPIError):
        await api.close()
        raise
