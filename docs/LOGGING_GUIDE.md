# AG-UI Server Logging Guide

## Overview

The `agui_server.py` now has comprehensive logging to track all user interactions, LLM operations, and system events.

## Log Locations

### 1. **Primary Log File** 📋
- **File**: `agui-server.log`
- **Location**: `/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/agui-server.log`
- **Contains**: All application logs (startup, requests, responses, errors)
- **Format**: `TIMESTAMP - LOGGER_NAME - LEVEL - MESSAGE`

### 2. **Console Output** 💻
- **Location**: Terminal where server is running
- **Contains**: Same logs as file (real-time)
- **Useful for**: Live monitoring during development

### 3. **LLM Configuration Logs** 🔑
- **File**: `.agent-session.log`
- **Contains**: Credential retrieval and LLM initialization logs from `llm_config.py`
- **Shared with**: `langchain-agent.py`

## What Gets Logged

### Server Startup
```
================================================================================
AWS Infra Agent Bot - AG-UI Server Starting
UI Directory: /Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/ui
================================================================================
Starting uvicorn server on http://0.0.0.0:8000
Reload mode: enabled
```

### API Requests

#### GET /api/models
```
API Request: GET /api/models - Listing available LLM providers
Returning 5 LLM providers
```

#### POST /api/run (User Query)
```
================================================================================
API Request: POST /api/run - New user query received
Provider: openai, Model: gpt-4o-mini
Credential Source: auto
Thread ID: abc123-def456-...
Message Length: 42 characters
Run ID: xyz789-abc123-...
Message ID: msg456-def789-...
Conversation history size: 2 messages
```

### LLM Operations
```
Initializing LLM - Provider: openai, Model: gpt-4o-mini, Credential Source: auto
LLM initialized and cached: openai:gpt-4o-mini:auto
LLM cache hit: openai:gpt-4o-mini:auto
```

### Stream Processing
```
[run-id] Stream started for thread thread-id
[run-id] Invoking LLM with conversation history
[run-id] LLM response generated - Length: 256 characters
[run-id] Updated conversation history size: 4 messages
[run-id] Stream completed successfully
```

### Errors
```
Request rejected: Empty message
Request rejected: Unsupported provider 'invalid-provider'
[run-id] LLM returned empty response
[run-id] Error during stream execution: Connection timeout
```

## Viewing Logs

### Real-time Monitoring
```bash
# Watch the log file in real-time
tail -f agui-server.log

# Watch with color highlighting (if you have ccze installed)
tail -f agui-server.log | ccze -A

# Watch last 50 lines and follow
tail -50f agui-server.log
```

### Search Logs
```bash
# Find all errors
grep "ERROR" agui-server.log

# Find logs for a specific run
grep "run-id-here" agui-server.log

# Find all user queries
grep "POST /api/run" agui-server.log

# Count requests by type
grep "API Request:" agui-server.log | cut -d'-' -f3 | sort | uniq -c
```

### View Recent Activity
```bash
# Last 20 lines
tail -20 agui-server.log

# Last 100 lines
tail -100 agui-server.log

# View with timestamps for today
grep "2026-02-08" agui-server.log
```

## Log Levels

The application uses standard Python logging levels:

- **DEBUG**: Detailed diagnostic information (cache hits, conversation history sizes)
- **INFO**: General informational messages (requests, responses, operations)
- **WARNING**: Warning messages (empty responses, validation issues)
- **ERROR**: Error messages (exceptions, failures)

## Log Rotation (Recommended)

For production, consider implementing log rotation to prevent the log file from growing too large:

```bash
# Using logrotate (Linux/macOS)
# Create /etc/logrotate.d/agui-server

/path/to/agui-server.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

Or modify the logging configuration in `agui_server.py` to use `RotatingFileHandler`:

```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'agui-server.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
```

## Privacy Considerations

**Important**: The current logging implementation does NOT log:
- ❌ Actual user query content (only message length)
- ❌ LLM response content (only response length)
- ❌ API keys or credentials

This is intentional for privacy and security. If you need to log query/response content for debugging, modify the log statements accordingly, but be cautious about sensitive data.

## Troubleshooting

### Log file not created
- Ensure the server has write permissions in the directory
- Check if the server is actually running
- Verify the file path in the logging configuration

### Logs not appearing
- Check the log level (set to INFO by default)
- Ensure you're looking at the correct file
- Verify the server has reloaded after code changes

### Too many logs
- Increase log level to WARNING or ERROR
- Implement log rotation
- Filter logs by specific criteria

## Example Log Session

```
2026-02-08 12:27:36,112 - agui_server - INFO - ================================================================================
2026-02-08 12:27:36,112 - agui_server - INFO - AWS Infra Agent Bot - AG-UI Server Starting
2026-02-08 12:27:36,112 - agui_server - INFO - UI Directory: /Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/ui
2026-02-08 12:27:36,112 - agui_server - INFO - ================================================================================
2026-02-08 12:27:59,205 - agui_server - INFO - API Request: GET /api/models - Listing available LLM providers
2026-02-08 12:27:59,205 - agui_server - INFO - Returning 5 LLM providers
2026-02-08 12:28:15,432 - agui_server - INFO - ================================================================================
2026-02-08 12:28:15,432 - agui_server - INFO - API Request: POST /api/run - New user query received
2026-02-08 12:28:15,432 - agui_server - INFO - Provider: openai, Model: default
2026-02-08 12:28:15,432 - agui_server - INFO - Credential Source: auto
2026-02-08 12:28:15,432 - agui_server - INFO - Thread ID: thread-123
2026-02-08 12:28:15,432 - agui_server - INFO - Message Length: 42 characters
2026-02-08 12:28:15,433 - agui_server - INFO - Run ID: run-456
2026-02-08 12:28:15,433 - agui_server - INFO - Message ID: msg-789
2026-02-08 12:28:15,433 - agui_server - DEBUG - Conversation history size: 0 messages
2026-02-08 12:28:15,434 - agui_server - INFO - [run-456] Stream started for thread thread-123
2026-02-08 12:28:15,434 - agui_server - INFO - [run-456] Invoking LLM with conversation history
2026-02-08 12:28:15,435 - agui_server - INFO - Initializing LLM - Provider: openai, Model: default, Credential Source: auto
2026-02-08 12:28:16,234 - agui_server - INFO - LLM initialized and cached: openai::auto
2026-02-08 12:28:18,567 - agui_server - INFO - [run-456] LLM response generated - Length: 256 characters
2026-02-08 12:28:18,567 - agui_server - DEBUG - [run-456] Updated conversation history size: 2 messages
2026-02-08 12:28:18,568 - agui_server - INFO - [run-456] Stream completed successfully
```

## Quick Reference

| Command | Purpose |
|---------|---------|
| `tail -f agui-server.log` | Watch logs in real-time |
| `grep ERROR agui-server.log` | Find all errors |
| `grep "run-id" agui-server.log` | Track specific request |
| `tail -100 agui-server.log` | View last 100 lines |
| `wc -l agui-server.log` | Count total log lines |

---

**Last Updated**: 2026-02-08
**Server Version**: AG-UI with comprehensive logging
