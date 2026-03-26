# FollowThru Architecture Diagrams

Generated on 24 Mar 2026 22:57.

This document contains the in-depth Mermaid source for the current FollowThru architecture and runtime flows.

## System HLD

High-level runtime architecture showing Slack, FastAPI, services, integrations, and persistence layers.

```mermaid
flowchart TD
    U1[Slack Channel User]
    U2[Slack DM User]
    U3[API Client]
    SL[Slack Workspace]
    NG[Public URL / ngrok]
    APP[FastAPI App]
    MID[HTTP Middleware\nrequest_id + process_time]
    RC1[/POST /slack/commands/]
    RC2[/POST /slack/interactions/]
    RC3[/POST /api/v1/followthru/chat/]
    RC4[/POST /api/v1/followthru/voice-command/]
    RC5[/POST /api/v1/workflows/preview/]
    RC6[/POST /api/v1/workflows/process-text/]
    BOLT[Slack Bolt App]
    CMD[Slack Command / DM Handlers]
    FTS[FollowThru Service]
    SR[Source Resolver]
    EXT[Extraction Service]
    OAI[OpenAI-Compatible Client]
    DRAFT[Draft Service]
    CANVAS[Canvas Composer]
    SCLI[Slack Client Wrapper]
    DB[(PostgreSQL)]
    S1[(users)]
    S2[(sources)]
    S3[(chat_sessions)]
    S4[(chat_messages)]
    S5[(drafts)]
    S6[(extracted_items)]

    U1 --> SL
    U2 --> SL
    SL --> NG --> APP --> MID
    U3 --> APP --> MID

    MID --> RC1 --> BOLT
    MID --> RC2 --> BOLT
    MID --> RC3 --> FTS
    MID --> RC4 --> FTS
    MID --> RC5 --> EXT
    MID --> RC6 --> FTS

    BOLT --> CMD
    CMD --> SR
    CMD --> EXT
    CMD --> DRAFT
    CMD --> FTS

    FTS --> SR
    FTS --> EXT
    FTS --> DRAFT
    DRAFT --> CANVAS
    SR --> SCLI
    DRAFT --> SCLI
    EXT --> OAI

    FTS --> DB
    SR --> DB
    DRAFT --> DB

    DB --> S1
    DB --> S2
    DB --> S3
    DB --> S4
    DB --> S5
    DB --> S6

    SCLI --> SL
```

## Channel Flow

End-to-end slash-command flow for resolving huddle notes, transcript fallback, extraction, and channel canvas publication.

```mermaid
sequenceDiagram
    autonumber
    actor User as Channel User
    participant Slack as Slack
    participant API as FastAPI /slack/commands
    participant Bolt as Slack Bolt
    participant Handler as commands.py
    participant Resolver as source_resolver.py
    participant SlackAPI as slack_client.py
    participant Extract as extraction_service.py
    participant Draft as draft_service.py
    participant Canvas as canvas_composer.py
    participant DB as PostgreSQL

    User->>Slack: Run /followthru or /followthru publish
    Slack->>API: POST /slack/commands
    API->>Bolt: handle_slack_request()
    Bolt->>Handler: handle_followthru_command()

    Handler->>Handler: Parse mode from command text
    alt help
        Handler-->>Slack: Ephemeral help text
    else clear in channel
        Handler-->>Slack: Ephemeral "clear only works in DM"
    else inline custom text in channel
        Handler-->>Slack: Redirect user to DM flow
    else preview or publish latest huddle
        Handler->>Resolver: resolve_latest_huddle_notes_canvas(channel_id, thread_ts, user_id)
        Resolver->>SlackAPI: files.list(channel, ts_from)
        SlackAPI-->>Resolver: files[]

        Resolver->>Resolver: pick latest filetype=canvas
        alt latest huddle canvas found
            Resolver->>SlackAPI: files.info(canvas_id)
            SlackAPI-->>Resolver: canvas content
        end

        alt canvas empty or thin
            Resolver->>Resolver: derive transcript name hints from canvas title/body
            Resolver->>Resolver: score transcript candidates by exact/partial name, text-likeness, timestamp proximity
            Resolver->>SlackAPI: files.info(best transcript id)
            SlackAPI-->>Resolver: merged transcript file details
            alt preview/content exists inline
                Resolver->>Resolver: use preview/content
            else downloadable file exists
                Resolver->>SlackAPI: download_text_file(url_private_download)
                SlackAPI-->>Resolver: transcript text
            end
        end

        Resolver->>Resolver: choose best source text
        Resolver->>DB: create Source(source_type=huddle_notes, raw_content_reference, slack_channel_id, slack_thread_ts, slack_canvas_id)
        Resolver-->>Handler: Source

        Handler->>Extract: extract_structured_meeting_data(raw_content)
        Extract->>Extract: normalize transcript
        alt input > extraction target
            Extract->>Extract: segment transcript
            Extract->>Extract: keep context segments
            Extract->>Extract: score segments by action/decision/risk/question/owner/date/high-signal keywords
            Extract->>Extract: compact transcript to dense subset
        end

        alt LLM configured
            Extract->>Extract: call OpenAI-compatible client via openai_client
            Extract-->>Handler: ExtractionResult from structured JSON
        else fallback parsing
            Extract->>Extract: deterministic rule parsing
            Extract->>Extract: detect action/decision/risk/question prefixes
            Extract->>Extract: infer owner via @mention regex
            Extract->>Extract: infer due dates via YYYY-MM-DD regex
            Extract->>Extract: derive title, summary, status, focus, owners, next review date
            Extract-->>Handler: ExtractionResult
        end

        alt preview
            Handler->>Handler: build ephemeral preview text
            Handler-->>Slack: Preview response only
        else publish
            Handler->>Draft: create_draft(owner_user_id, source, extraction, publish_to_slack=True)
            Draft->>Canvas: create_draft_canvas(extraction, source_label, title_override)
            Draft->>DB: insert Draft
            Draft->>DB: insert ExtractedItem rows for summary, decisions, action items, questions, risks
            alt Slack publishing enabled + configured + channel_id exists
                Draft->>SlackAPI: upload_canvas(channel_id=C..., content, title)
                alt no existing conversation canvas
                    SlackAPI-->>Draft: conversations.canvases.create(canvas_id)
                else existing channel canvas already exists
                    SlackAPI->>SlackAPI: conversations.info(channel)
                    SlackAPI->>SlackAPI: canvases.edit(replace content)
                    SlackAPI-->>Draft: existing canvas id
                end
            end
            Draft-->>Handler: Draft + canvas markdown
            Handler-->>Slack: Ephemeral success/fallback message
        end
    end
```

## DM Flow

Deep DM workflow including file ingestion, transcript artifact upload, session persistence, extraction, and standalone canvas publication.

```mermaid
sequenceDiagram
    autonumber
    actor User as DM User
    participant Slack as Slack DM
    participant API as FastAPI /slack/interactions or events
    participant Bolt as Slack Bolt
    participant Handler as commands.py
    participant SlackAPI as slack_client.py
    participant FTS as followthru_service.py
    participant Resolver as source_resolver.py
    participant Extract as extraction_service.py
    participant Draft as draft_service.py
    participant Canvas as canvas_composer.py
    participant DB as PostgreSQL

    User->>Slack: Send DM text or transcript file
    Slack->>API: message event
    API->>Bolt: handle_slack_request()
    Bolt->>Handler: handle_followthru_dm(event, say)

    Handler->>Handler: ignore non-IM channels
    Handler->>Handler: ignore bot messages and message_changed

    Handler->>Handler: build DMSourcePayload
    alt plain text message
        Handler->>Handler: collect message text
    end
    alt file(s) attached
        loop each file
            Handler->>Handler: hydrate file metadata if needed
            alt supported text-like file (.txt/.md/.csv/.tsv/.srt/.vtt/.log)
                alt inline preview exists
                    Handler->>Handler: use preview text
                else downloadable
                    Handler->>SlackAPI: download_text_file(url)
                    SlackAPI-->>Handler: file text
                end
            else supported docx
                Handler->>SlackAPI: download_file_bytes(url)
                SlackAPI-->>Handler: binary bytes
                Handler->>Handler: unzip word/document.xml
                Handler->>Handler: extract paragraph text from DOCX XML
            else unsupported or unreadable
                Handler->>Handler: mark file unsupported/unreadable
            end
        end
    end

    alt no usable text
        Handler-->>Slack: file support / help guidance
    else help/hi/hello
        Handler-->>Slack: DM help text
    else usable transcript
        Handler-->>Slack: post "Processing your transcript..."
        Handler->>Handler: capture status message channel+ts
        alt long pasted message >= threshold
            Handler->>SlackAPI: files_upload_v2(transcript artifact .txt)
            SlackAPI-->>Handler: uploaded file metadata
        end

        Handler->>FTS: handle_followthru_chat(message=_normalize_dm_request(payload.text), user_id, channel_id=D..., thread_ts)
        FTS->>FTS: parse mode (help/chat/preview/draft/publish)
        FTS->>DB: get or create ChatSession
        FTS->>DB: insert ChatMessage(role=user)

        alt mode is help
            FTS-->>Handler: FollowThruResponse(help)
        else mode is preview/draft/publish
            alt request explicitly says latest huddle OR notes missing
                FTS->>Resolver: resolve_latest_huddle_notes_canvas(...)
                Resolver-->>FTS: Source from channel-style lookup
            else inline/file transcript present
                alt source should persist (draft/publish/voice-preview)
                    FTS->>DB: create Source(source_type=text or voice)
                end
            end

            FTS->>Extract: extract_structured_meeting_data(raw_content)
            Extract-->>FTS: ExtractionResult

            alt preview
                FTS->>Canvas: create_draft_canvas(...)
                FTS-->>Handler: preview response + markdown
            else draft or publish
                FTS->>Draft: create_draft(...)
                Draft->>Canvas: create_draft_canvas(...)
                Draft->>DB: insert Draft
                Draft->>DB: insert ExtractedItem rows
                alt publish_to_slack and DM channel
                    Draft->>SlackAPI: canvases.create(title, markdown)
                    alt owner slack user id available
                        Draft->>SlackAPI: canvases.access.set(write access to user)
                    end
                    SlackAPI-->>Draft: standalone canvas id
                end
                Draft-->>FTS: draft + markdown
                FTS-->>Handler: response with reply, draft title, slack canvas id, canvas markdown
            end
        else plain chat
            alt LLM configured
                FTS->>FTS: send recent session history + user input to openai_client.generate_followthru_reply()
            else deterministic reply
                FTS->>FTS: return canned capability/status reply
            end
            FTS-->>Handler: chat response
        end

        FTS->>DB: insert ChatMessage(role=assistant)
        FTS->>DB: update ChatSession.updated_at/title
        Handler->>Handler: build final DM message
        Handler->>Handler: append notices for uploaded file processed / transcript artifact saved / skipped files
        alt status message can be updated
            Handler->>SlackAPI: chat.update(processing message -> final message)
        else update fails
            Handler-->>Slack: send new completion message
        end
    end
```

## Direct API Flow

Non-Slack API routes for preview, process-text, chat, and voice-command.

```mermaid
flowchart TD
    A[Client POST /api/v1/followthru/chat] --> B[followthru_chat route]
    B --> C[handle_followthru_chat]
    C --> D[_handle_followthru_input]
    D --> E[Parse mode + create/load ChatSession]
    E --> F[Store user ChatMessage]
    F --> G{Mode}
    G -->|chat| H[LLM chat or deterministic reply]
    G -->|preview/draft/publish| I[_execute_canvas_request]
    I --> J{Use latest huddle?}
    J -->|yes| K[resolve_latest_huddle_notes_canvas]
    J -->|no| L[create Source if persistence needed]
    K --> M[extract_structured_meeting_data]
    L --> M
    M --> N{preview?}
    N -->|yes| O[create_draft_canvas only]
    N -->|no| P[create_draft]
    P --> Q[optional Slack canvas publish]
    H --> R[Store assistant ChatMessage]
    O --> R
    Q --> R
    R --> S[Return FollowThruResponse]

    A2[Client POST /api/v1/followthru/voice-command] --> B2[followthru_voice_command route]
    B2 --> C2[handle_followthru_voice_command]
    C2 --> D

    A3[Client POST /api/v1/workflows/preview] --> B3[preview_workflow]
    B3 --> C3[extract_structured_meeting_data]
    C3 --> D3[create_draft_canvas]
    D3 --> E3[return extraction + markdown only]

    A4[Client POST /api/v1/workflows/process-text] --> B4[process_text_workflow]
    B4 --> C4[create_text_source]
    C4 --> D4[extract_structured_meeting_data]
    D4 --> E4[create_draft]
    E4 --> F4[return source_id + draft_id + extraction + canvas]
```

## Persistence Model

Core relational persistence model for users, sources, sessions, drafts, and extracted items.

```mermaid
erDiagram
    USERS ||--o{ SOURCES : creates
    USERS ||--o{ CHAT_SESSIONS : owns
    CHAT_SESSIONS ||--o{ CHAT_MESSAGES : contains
    SOURCES ||--o{ DRAFTS : feeds
    DRAFTS ||--o{ EXTRACTED_ITEMS : contains

    USERS {
        uuid id
        string slack_user_id
        string name
        string email
        datetime created_at
    }

    SOURCES {
        uuid id
        enum source_type
        string slack_channel_id
        string slack_thread_ts
        string slack_canvas_id
        string raw_content_reference
        uuid created_by
        datetime created_at
    }

    CHAT_SESSIONS {
        uuid id
        string bot_name
        uuid user_id
        string slack_channel_id
        string slack_thread_ts
        string title
        datetime created_at
        datetime updated_at
    }

    CHAT_MESSAGES {
        uuid id
        uuid session_id
        enum role
        text content
        datetime created_at
    }

    DRAFTS {
        uuid id
        uuid owner_user_id
        uuid source_id
        string slack_canvas_id
        string title
        enum status
        datetime created_at
        datetime updated_at
    }

    EXTRACTED_ITEMS {
        uuid id
        uuid draft_id
        enum item_type
        string content
        enum confidence
        string assignee
        date due_date
        datetime created_at
    }
```
