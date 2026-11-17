# H14 — native secure-entry paste correction

B1 user acceptance found that typing worked in `NSSecureTextField` but Cmd+V did
not paste. The absence/routing of an Edit menu in the GPUI host is a plausible
explanation, not a measured cause. The fix is local to the AppKit sheet:

- Its accessory view contains the secure field and a visible **Pegar** button.
- That button owns Cmd+V and targets only its enrollment object.
- The action requires the main thread, `awaiting_user`, no cancellation, and the
  field still attached to this alert's window. It preserves the current editor
  when present, otherwise focuses that exact secure field, then sends AppKit's
  `paste:` action to its field editor.
- It does not obtain a pasteboard string or place clipboard contents in Rust,
  bridge JSON, MCP, diagnostics, logs, arguments or environment. No global menu
  or GPUI event handler changes. Existing validation, native storage/wiping,
  cancellation and receipt barriers remain in place; the C ABI is unchanged.

Apple documents the button's key-equivalent dispatch, the control's own field
editor, and `paste:` inserting clipboard text through AppKit:
[NSButton keyEquivalent](https://developer.apple.com/documentation/appkit/nsbutton/keyequivalent),
[NSControl currentEditor](https://developer.apple.com/documentation/appkit/nscontrol/currenteditor()),
[NSText paste](https://developer.apple.com/documentation/appkit/nstext/paste(_:)).

`scripts/fixtures/h14_secure_paste_test.m` is an isolated native routing test.
It creates only a unique private pasteboard containing synthetic owned text;
the editor test double redirects `paste:` to that board. It checks button and
Cmd+V action routing without an Edit menu and rejects paste after submission,
cancellation or detachment. It never uses the general pasteboard, Keychain,
capture, networking or real credentials. No field text is printed.

Coordinating owner may compile/run after B1 closes and outside measurements:

```sh
clang -arch arm64 -mmacosx-version-min=15.0 -fobjc-arc -fblocks \
  -Wall -Wextra -Werror -Wno-deprecated-declarations \
  -framework AppKit -framework Security \
  scripts/fixtures/h14_secure_paste_test.m -o target/h14-secure-paste-test
target/h14-secure-paste-test
```

The coordinating owner compiled and ran this native routing test successfully;
evidence: `var/evidence/h14-build/secure-paste-native-test.log`. This does not
prove the complete GPUI→native keyboard path. The visible button and Cmd+V
still require verification in the rebuilt signed sheet; the user's actual clipboard must remain confined
to their native entry, without tool inspection or screenshots of field content.

## B2 user verification

The signed B2 sheet exposes **Pegar** and the native secure field. The user
reported that pasting and saving succeeded. The owner then observed
`phase: stored`, `attached: true`, `receipt_persisted: true`, no reconciliation,
and no credential operation still busy. Evidence is in
`var/evidence/h14-portable-b2-1794953837847861000/`:
`destination-enrollment-completed.json` and `secure-paste-ui-verification.json`.
No tool inspected the clipboard or entered the key. The report verifies the
button workflow; a separate physical Cmd+V test remains unverified.
