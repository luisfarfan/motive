# Show Control: evidence and bounded roadmap

Research date: 2026-11-17. Motive baseline: `b52d135` (H12). This is documentary
research against public official documentation and Motive's source. No competitor
application, device, provider account or live output was operated. No performance
comparison was made. Documentation does not prove the behavior of an installed
version. REA was unnecessary: the decisions below do not require proprietary
implementation details.

## Comparative evidence

| Concern | Streamer.bot | StreamElements | Meld Studio | Motive decision |
|---|---|---|---|---|
| Events and actions | One action can have multiple triggers and sub-actions; trigger arguments carry context. [Introduction](https://docs.streamer.bot/get-started/introduction/) | Widget lifecycle and activity listeners include chat, follows, subscriptions, tips and moderation deletions. [Widget events](https://docs.streamelements.com/overlays/events) | Native widgets respond to connected platform activity; event support differs by platform. [Widgets](https://meldstudio.co/docs/widget/) | A platform-neutral, versioned event with a validated tagged payload, provenance and correlation ID. External data cannot be a command. |
| Conditions and state | If/Else supports variable comparison; variables include execution arguments and globals. [Conditions](https://docs.streamer.bot/api/sub-actions/core/logic/if-else), [variables](https://docs.streamer.bot/guide/core/variables) | Fields supply editable properties; session data supplies activity totals. [Events and field data](https://docs.streamelements.com/overlays/events) | Inspector edits appearance and behavior of widgets. [Widgets](https://meldstudio.co/docs/widget/) | Bounded typed conditions and local variables, without expressions, regex execution or scripting. |
| Cooldowns and permission | Commands have enabled state, global/user cooldowns and allow/deny groups. The broadcaster has documented exemptions. [Commands](https://docs.streamer.bot/guide/core/commands) | Alert widgets manage event presentation. | Integrated events and per-widget filters are documented. | Explicit authorization, cooldown and debounce policies; no implicit owner exemption. |
| Ordering and concurrency | Blocking queues begin the next action after the previous finishes. History includes pending/completed/cancelled state. [Queues](https://docs.streamer.bot/faq/action-blocking), [actions](https://docs.streamer.bot/guide/core/actions) | `widgetDuration` holds queued events; `resumeQueue` releases early. Some event kinds bypass that queue. [SE_API](https://docs.streamelements.com/overlays/custom-widget) | Streamer.bot integration can control scenes/layers and exposes connection configuration. [Integration](https://meldstudio.co/docs/integrations/streamerbot/) | One bounded priority/FIFO scheduler, observable outcomes, no sleeps to advance media. |
| Errors and completion | Break stops the current action. Reviewed docs do not establish atomic rollback of sub-actions or exactly-once delivery. [Break](https://docs.streamer.bot/api/sub-actions/core/logic/break) | Queue release is not evidence that an external media operation completed. | Reviewed pages do not define transactional action sequences or rollback. | Acceptance and media completion differ; stop failed sequences, preserve partial results, reconcile uncertain dispatch without automatic retry. |
| Reusable visuals | Actions compose capabilities of connected applications. | AlertBox properties include image, sound, text, layout and duration; custom widgets permit HTML/CSS/JS. [Alerts](https://docs.streamelements.com/selive/guides/overlays-and-alerts) | Chat/activity/spotlight/combo/countdown and other widgets are integrated. [Widgets](https://meldstudio.co/docs/widget/) | Declarative original packs using existing native text/shapes/widgets/animations; no remote browser content or pack code. |

Meld's integration documentation demonstrates an automation route through
Streamer.bot, including scene/layer control and triggers; it does **not** establish
an independent general-purpose rule editor inside Meld. The opportunity is a
small inspectable Show Control definition sharing Motive's typed control plane.
It does not require reproducing competitor internals, artwork or UI.

## Minimum architecture

Use one independent Rust library for validation, bounded rules, local variables,
queue decisions and intent preparation. A deterministic simulator supplies a
monotonic clock and synthetic production context. A later owner-side adapter
checks the real `Production` and translates approved intents to existing
commands. Read-only context is a disposable snapshot, never a second scene graph
or multimedia clock. The pack planner describes proposed installation; it does
not install into Motive. See [integration contract](integration.md).

## Voice: future pipeline, no capture implemented

The [whisper.cpp project](https://github.com/ggml-org/whisper.cpp) provides local
inference, Apple Silicon support and VAD facilities. Its
[stream example](https://github.com/ggml-org/whisper.cpp/blob/master/examples/stream/README.md)
is explicitly a simple real-time example that opens its own microphone using
SDL2. It is not the integration path for Motive. Its example intervals are not
latency measurements for this Mac or a promise about captions.

Proposed increment, dependent on an H13-reviewed audio contract:

1. Add an opt-in bounded PCM tap to the existing mixer owner. Choose the intended
   microphone/input or mix explicitly; do not capture another microphone or feed
   program audio back into keyword detection. Specify sample format, timebase,
   discontinuity markers and drop counters before implementation.
2. Copy into a bounded worker queue, resample there if needed, and run VAD then
   inference outside the audio callback. Never block the mixer. Queue overflow,
   input removal and sleep invalidate pending segments.
3. Ship no model automatically. Offer optional checksum-pinned downloads with
   size, model license, language coverage and deletion controls; use a local
   model when selected. Compare English-only and multilingual Spanish/English
   models using owned recordings, crosstalk, silence and football commentary.
4. Separate caption partials from committed segments. Only committed segments
   may emit `voice.keyword_detected`; deduplicate overlapping windows by segment
   identity and enforce phrase boundaries, cooldown and a local armed state.
5. Model token probability is not calibrated speaker/command confidence. A
   trusted adapter must declare the scoring method and model identity before a
   confidence condition can be relied upon. JSON claiming high confidence is
   insufficient. Test false activations from speakers, music and quoted words.
6. Measure audio-end-to-committed-text and audio-end-to-accepted-action p50/p95,
   CPU/RSS, dropped PCM, false-positive/negative rates, languages and model hash.
   Set a latency budget only after these measurements. Keep audio/transcripts
   transient by default; explicit consent is needed for retained diagnostics.

Live captions need a separate bounded partial/final transcript contract and an
approved existing text overlay. They must not rewrite text every audio frame.
Soundboard and TTS require an owned audio playback source with gain, stop,
ducking policy and output/monitoring semantics. Preparing text is not synthesis;
neither capability is available in this increment.

## Provider adapters: future contracts

An adapter must authenticate its transport, bind a provider/account/channel,
validate a bounded native payload, produce normalized events, and supply trusted
identity/role/confidence evidence separately from viewer text. It must expose
connection state (`disconnected`, `connecting`, `ready`, `backoff`, `revoked`),
last error and dropped-event counts without tokens. The central runtime remains
provider-independent; this increment contains no network connector.

| Input | Official API and minimum intended scope | Normalization notes |
|---|---|---|
| Twitch chat | `channel.chat.message`, user-token `user:read:chat`; extra bot grants depend on the app-token route. [Chat reference](https://dev.twitch.tv/docs/eventsub/reference/chat) | `chat.message`; parse a bounded command into `chat.command`. Authorize stable user IDs/verified roles, never a display name or text saying “moderator.” |
| Twitch follow | `channel.follow` v2, `moderator:read:followers` and matching broadcaster/moderator identity. [Channel reference](https://dev.twitch.tv/docs/eventsub/reference/channel) | `viewer.follow`; bind the subscription's channel. |
| Twitch subscription | `channel.subscribe`, `channel.subscription.gift` and `channel.subscription.message`, `channel:read:subscriptions`. [Channel reference](https://dev.twitch.tv/docs/eventsub/reference/channel) | Keep event subtype; a resubscription message differs from a new subscription. Gift summary/member events need an explicit anti-double-count policy. |
| Twitch Bits | `channel.cheer` or the newer `channel.bits.use`, `bits:read`. [Channel reference](https://dev.twitch.tv/docs/eventsub/reference/channel) | Select one overlapping stream or deduplicate deliberately; Bits are not a currency donation. Preserve units in a custom event until a dedicated payload exists. |
| Twitch rewards | `channel.channel_points_custom_reward_redemption.add`, `channel:read:redemptions` for observation. [Channel Points](https://dev.twitch.tv/docs/eventsub/reference/channel-points) | `viewer.reward_redeemed`, stable redemption/reward IDs. Do not request manage scope merely to observe. |
| Twitch charity | `channel.charity_campaign.donate`, `channel:read:charity`. [Scopes](https://dev.twitch.tv/docs/authentication/scopes/), [Charity reference](https://dev.twitch.tv/docs/eventsub/reference/charity) | Charity beneficiary, currency and amount must remain distinct from tips paid to a creator. |
| YouTube chat/support | `liveChatMessages` provides text, membership, Super Chat and Super Sticker details. [Resource](https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages) | Preserve message ID, `publishedAt`, author identity and subtype. Super Chat uses integer `amountMicros` and currency; do not parse localized display money. Stickers are metadata, not permission to auto-fetch an image. |
| Other donations/tips | StreamElements documents `tip-latest` in its widget surface. [Events](https://docs.streamelements.com/overlays/events) | That browser event is not proof of a signed server API suitable for Motive. A future connector must first verify the provider's supported authentication/delivery contract. No generic “donation webhook” is trusted. |

Twitch WebSocket EventSub suits a desktop client because it does not require a
public inbound server. It uses user access tokens, welcome/subscription state,
keepalives, reconnect and revocation. A normal disconnect requires new
subscriptions and does not replay the outage; a server-directed reconnect has a
different continuity flow. Report gaps instead of inventing missing events.
[Twitch lifecycle](https://dev.twitch.tv/docs/eventsub/handling-websocket-events).
Delivery is at least once, with the same message ID on resend: persist a bounded
deduplication ledger keyed by provider/account and message ID.
[WebSocket reference](https://dev.twitch.tv/docs/eventsub/websocket-reference).

YouTube now documents `liveChatMessages.streamList`: initial history arrives on
connection, and `nextPageToken` resumes after disconnect. A bootstrap policy
must avoid treating historical support as new on-air actions.
[streamList](https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages/streamList).
If the polling method is used, honor `pollingIntervalMillis`, page tokens and
quota errors; `liveChatEnded`/`liveChatDisabled` are not transient retry loops.
[list](https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages/list).
An authorized read-only Google flow is the intended starting point; confirm
method-specific scopes at connector implementation rather than request write
privileges. [YouTube authentication](https://developers.google.com/youtube/v3/guides/authentication).

## Security and acceptance gates for connectors

- OAuth is a local user flow. Keep refresh/access tokens in macOS Keychain under
  H8's identity/access policy; expose opaque references only. No token fields in
  rules, packs, events, MCP responses or diagnostic logs. Token refresh belongs
  to the adapter and is never performed by a rule.
- Bind credentials and subscriptions to the expected channel. Verify TLS and
  hostnames. Webhook support, if ever added, needs signature/timestamp/replay
  verification before normalization; it is not needed for the first local
  WebSocket adapter.
- Treat names/messages as untrusted bounded text. No HTML, scripts, file paths,
  URL fetches, commands or rule installation from viewer content. Apply moderation
  removals to queued presentations; never accept user-supplied role claims.
- Backoff and provider retry hints govern reconnection/subscription reads. A
  transport retry does not authorize replaying a multimedia mutation. Persist
  dedup/cursor state, disclose its retention horizon, and quarantine uncertainty.
- First live acceptance: a separate authorized account test, owned content,
  duplicate/reconnect/revocation fixtures, queue bounds, moderator permissions,
  Keychain denial and logs checked for secrets. No provider connection, OAuth,
  STT, TTS, sound playback or public transmission was performed here.
