"""
Kitee

Copyright (c) 2026 Kitee Contributors. All rights reserved.

Original repository:

Copyright (c) 2024~2025 Techarerm/TedKai
"""
import json
import threading
from urllib.parse import parse_qs, urlparse
from ..bk_core.account.account_management import (
    check_account_data_format,
    check_target_account_exists_using_uuid,
    create_account_data,
    delete_specified_account_data,
    get_account_data_use_account_id,
    get_all_available_accounts,
    get_current_account_id,
    set_current_account_id,
    update_specified_account_data,
    write_new_account_to_account_data,
) # IMPORTANT: All functions inside account_management are not support PathLib.Path object as the value of the path
# arguments. Convert it into string before you use it !!!
from ..bk_core.account.auth_process import get_account_token_msa
from ..bk_core.account.mojang_api import check_access_token_are_valid, get_account_username_and_uuid

CLIENT_ID = "00000000402B5328" # from official Minecraft Launcher

class AccountManager:
    LOGIN_URL = (
        "https://login.live.com/oauth20_authorize.srf"
        f"?client_id={CLIENT_ID}"
        "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
        "&response_type=code"
        "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    )
    REDIRECT_HOST = "login.live.com"
    REDIRECT_PATH = "/oauth20_desktop.srf"

    def __init__(self, gui, data_dir, logger):
        self.gui = gui

        # Directories
        self.data_dir = data_dir
        self.account_data_path = data_dir / "accounts.json" # Operate account data lock

        # Logger
        self.logger = logger

        # Lock
        self.lock = threading.Lock()

        # Window & Flags
        self.login_window = None
        self.login_in_progress = False

    @staticmethod
    def _avatar_url(uuid):
        """Return 64x64 pixel specified uuid player's avatar."""
        return f"https://mc-heads.net/avatar/{uuid}/64"

    def get_accounts(self):
        """
        Get full accounts list. (FrontOnly)
        """
        with self.lock:
            status, message = self.ensure_account_data()
            if not status:
                return {"ok": False, "error": message, "accounts": []}

            status, accounts, error = get_all_available_accounts(str(self.account_data_path))
            if not status:
                return {"ok": False, "error": error, "accounts": []}

            status, current_id, _ = get_current_account_id(str(self.account_data_path))
            if not status:
                current_id = None

            items = []
            for entry in accounts:
                for account_id, username in entry.items():
                    status, account, _ = get_account_data_use_account_id(str(self.account_data_path), account_id)
                    if not status:
                        account = {}
                    elif account_id == current_id:
                        self.refresh_account_session(account_id, account)

                    items.append({
                        "id": account_id,
                        "username": account.get("Username") or username,
                        "uuid": account.get("UUID", ""),
                        "type": account.get("AccountType", ""),
                        "tag": account.get("tag", ""),
                        "current": account_id == current_id,
                        "avatar": self._avatar_url(account.get("UUID", "")),
                    })

            return {
                "ok": True,
                "currentAccountId": current_id,
                "accounts": items,
            }

    def create_offline_account(self, username):
        """
        Create offline account

        IMPORTANT: Only use when logged account are exist.
        """
        username = str(username or "").strip()

        if not username:
            return {"ok": False, "error": "Username is required."}

        with self.lock:
            status, message = self.ensure_account_data()
            if not status:
                return {"ok": False, "error": message}

            status, account_id, error = write_new_account_to_account_data(
                str(self.account_data_path),
                username,
                "00000000-0000-0000-0000-000000000000",
                None,
                "offline",
                "offline",
            )
            if not status:
                return {"ok": False, "error": str(error)}

            if account_id is not None:
                set_current_account_id(str(self.account_data_path), account_id)

            return {"ok": True, "accountId": account_id}

    def switch_account(self, account_id):
        """Switch current account id."""
        with self.lock:
            status, message = self.ensure_account_data()
            if not status:
                return {"ok": False, "error": message}

            status, error = set_current_account_id(str(self.account_data_path), account_id)
            if not status:
                return {"ok": False, "error": str(error)}

            return {"ok": True}

    def delete_account(self, account_id):
        """Delete specified account by account id."""
        with self.lock:
            status, message = self.ensure_account_data()
            if not status:
                return {"ok": False, "error": message}

            status, error = delete_specified_account_data(str(self.account_data_path), account_id)
            if not status:
                return {"ok": False, "error": str(error)}

            status, current_id, _ = get_current_account_id(str(self.account_data_path))
            if status and current_id == account_id:
                set_current_account_id(str(self.account_data_path), None)

            return {"ok": True}

    def clear_account_data(self):
        with self.lock:
            self.account_data_path.parent.mkdir(parents=True, exist_ok=True)
            status = create_account_data(str(self.account_data_path), overwrite=True)
            if not status:
                return {"ok": False, "error": "Failed to clear AccountData."}

            return {"ok": True}

    def start_msa_login(self):
        """
        Open login window. (embedded webview)
        :return:
        """
        try:
            import webview

            if self.login_window:
                try:
                    self.login_window.restore()
                except Exception:
                    pass
                return {"ok": True, "alreadyOpen": True}

            self.login_in_progress = False
            self.login_window = webview.create_window(
                "Microsoft Login",
                url=self.LOGIN_URL,
                width=520,
                height=720,
                min_size=(420, 520),
            )
            self.login_window.events.request_sent += self.handle_login_request
            self.login_window.events.closed += self.handle_login_closed
            return {"ok": True}
        except Exception as exc:
            self.logger.exception("Failed to open Microsoft login window.")
            self.login_window = None
            return {"ok": False, "error": str(exc)}

    def handle_login_request(self, request):
        code = self.extract_auth_code(request.url)
        if not code or self.login_in_progress:
            return

        self.login_in_progress = True
        self.notify_login_status("Signing in...")

        window = self.login_window
        self.login_window = None

        try:
            if window:
                window.destroy()
        except Exception:
            self.logger.exception("Failed to close Microsoft login window.")

        threading.Thread(target=self.complete_msa_login, args=(code,), daemon=True).start()

    def handle_login_closed(self):
        self.login_window = None

    def complete_msa_login(self, code):
        self.notify_login_status("Exchanging Microsoft token...")
        status, access_token, refresh_token, error = get_account_token_msa(code,
                                                                           client_id=CLIENT_ID)
        if not status:
            self.notify_login_status("Login failed: {}".format(error))
            return

        self.notify_login_status("Loading Minecraft profile...")
        status, username, uuid, error = get_account_username_and_uuid(access_token)
        if not status:
            self.notify_login_status("Failed to get Minecraft profile: {}".format(error))
            return

        with self.lock:
            status, message = self.ensure_account_data()
            if not status:
                self.notify_login_status(message)
                return

            exists_status, account_id, _ = check_target_account_exists_using_uuid(str(self.account_data_path), uuid)
            if not exists_status:
                status, account_id, error = write_new_account_to_account_data(
                    str(self.account_data_path),
                    username,
                    uuid,
                    refresh_token,
                    access_token,
                    "msa",
                )
                if not status:
                    self.notify_login_status("Failed to add account: {}".format(error))
                    return
            else:
                status, error = update_specified_account_data(
                    str(self.account_data_path),
                    account_id,
                    username,
                    refresh_token,
                    access_token,
                    tag="",
                    account_type="msa",
                )
                if not status:
                    self.notify_login_status("Failed to update account: {}".format(error))
                    return

            set_current_account_id(str(self.account_data_path), account_id)

        self.notify_login_status("Login success: {}".format(username))
        self.notify_accounts_changed()

    def extract_auth_code(self, url):
        parsed_url = urlparse(str(url))
        if parsed_url.netloc != self.REDIRECT_HOST or parsed_url.path != self.REDIRECT_PATH:
            return None

        query = parse_qs(parsed_url.query)
        codes = query.get("code")
        if not codes:
            return None

        return codes[0]

    def notify_login_status(self, message):
        self.gui.evaluate_main_js("window.__bakeAccountStatus && window.__bakeAccountStatus({});".format(
            json.dumps(message)
        ))

    def notify_accounts_changed(self):
        self.gui.evaluate_main_js("window.__bakeAccountsChanged && window.__bakeAccountsChanged();")

    def ensure_account_data(self):
        self.account_data_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.account_data_path.exists():
            if create_account_data(str(self.account_data_path)):
                return True, None
            return False, "Failed to create AccountData."

        status, _ = check_account_data_format(str(self.account_data_path))
        if status:
            return True, None

        if create_account_data(str(self.account_data_path), overwrite=True):
            return True, None

        return False, "AccountData format is invalid and could not be overwritten."

    def get_current_account_data_for_launch(self):
        with self.lock:
            status, message = self.ensure_account_data()
            if not status:
                return False, message

            curr_acc_id = get_current_account_id(str(self.account_data_path))

            if not curr_acc_id[0] or not curr_acc_id[1]:
                return False, "No current account selected."

            curr_acc_data = get_account_data_use_account_id(str(self.account_data_path), curr_acc_id[1])
            if not curr_acc_data[0] or not curr_acc_data[1]:
                return False, "Failed to get current account data."

            account = curr_acc_data[1]
            return self.refresh_account_session(curr_acc_id[1], account)

    def refresh_account_session(self, account_id, account):
        if str(account.get("AccountType") or "").lower() != "msa":
            return True, account

        access_token = account.get("AccessToken")
        if access_token and check_access_token_are_valid(access_token):
            if account.get("tag") == "Expired":
                self.update_account_tag(account_id, "")
                account["tag"] = ""
            return True, account

        refresh_token = account.get("RefreshToken")
        if not refresh_token:
            self.mark_account_expired(account_id, account)
            return False, "Microsoft account session expired. Please sign in again."

        self.logger.info("Refreshing Microsoft account token for account id %s.", account_id)
        status, new_access_token, new_refresh_token, error = get_account_token_msa(refresh_token,
                                                                                   refresh_code=True,
                                                                                   client_id=CLIENT_ID)
        if not status:
            self.mark_account_expired(account_id, account)
            return False, "Microsoft account session refresh failed: {}".format(error)

        status, username, uuid, error = get_account_username_and_uuid(new_access_token)
        if not status:
            self.mark_account_expired(account_id, account)
            return False, "Failed to get Minecraft profile after refreshing session: {}".format(error)

        status, error = update_specified_account_data(
            str(self.account_data_path),
            account_id,
            username,
            new_refresh_token,
            new_access_token,
            tag="",
            uuid=uuid,
            account_type="msa",
        )
        if not status:
            return False, "Failed to save refreshed account session: {}".format(error)

        account.update({
            "Username": username,
            "UUID": uuid,
            "RefreshToken": new_refresh_token,
            "AccessToken": new_access_token,
            "AccountType": "msa",
            "tag": "",
        })
        return True, account

    def mark_account_expired(self, account_id, account):
        self.update_account_tag(account_id, "Expired")
        account["tag"] = "Expired"

    def update_account_tag(self, account_id, tag):
        status, error = update_specified_account_data(
            str(self.account_data_path),
            account_id,
            "!skip",
            "!skip",
            "!skip",
            tag=tag,
        )
        if not status:
            self.logger.warning("Failed to update account tag for account id %s: %s", account_id, error)
        return status
