# v0.3.5 - The password binding is verified, not assumed

English (this page) · <a id="chinese">中文说明 ↓</a> · Released 2026-10-20

The panel password has been copied into the WebUI `.env` since v0.3.1, but nothing **checked**
it: once the two drifted apart the card still looked bound, and the phone login failed with
"Invalid password".

**Now the backend verifies it.** Every WebUI status snapshot runs the `.env` password against
the panel's `scrypt` hash (`_panel_hash_ok`). The card shows `✓ 已与面板同一个密码` only when it
truly matches; otherwise the `与面板密码绑定` button comes back so you can repair it in one click.
The LAN card's password row also shows the *effective* string once bound, in both phone-page modes.

## SHA256

```
4976b28ea01f3b7ba1311774f0b84716d8e1c4d2d6fab29d0ed5a7bcfc695a1e  phone-remote-v0.3.5-plugin.zip
ebe99fa42ed77fb8710335be13704f5bd785d90c25e5f7037ff9c57c36e931c8  phone-remote-v0.3.4-to-v0.3.5-update.zip
```

---

<a id="chinese"></a>

# v0.3.5 - 密码绑定是验出来的，不是嘴上说说

v0.3.1 起改面板密码会把同一串写进网页版 `.env`，但**没人去验**：两处一旦漂移，卡片照样
看着像绑定好的，手机上却报 Invalid password。

**现在后端每次都验**：拿网页版 `.env` 里那串跑一遍面板的 `scrypt` hash（`_panel_hash_ok`），
真一样才显示「✓ 已与面板同一个密码」，不一样就把「与面板密码绑定」按钮还给用户点一下修好。
已绑定时，局域网卡的密码行显示的就是真正有效的那串（两种手机页面都对）。

## SHA256

```
4976b28ea01f3b7ba1311774f0b84716d8e1c4d2d6fab29d0ed5a7bcfc695a1e  phone-remote-v0.3.5-plugin.zip
ebe99fa42ed77fb8710335be13704f5bd785d90c25e5f7037ff9c57c36e931c8  phone-remote-v0.3.4-to-v0.3.5-update.zip
```
