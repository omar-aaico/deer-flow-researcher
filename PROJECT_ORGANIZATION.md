# DeerFlow Project Organization

## 📁 Folder Structure

```
deer-flow/
├── education/          # 📚 All guides and documentation
│   ├── README.md
│   ├── 08-understanding-thread-id-and-results.md  # ⭐ START HERE
│   ├── 09-async-api-guide.md                      # Complete async guide
│   └── 10-async-api-summary.md                    # Quick reference
│
├── tests/manual/       # 🧪 All test scripts
│   ├── README.md
│   ├── test_async_api.py           # ⭐ RECOMMENDED test
│   ├── test_streaming_explained.py  # Educational streaming demo
│   ├── test_get_final_answer.py     # Clean result extraction
│   └── test-console.html            # Browser-based testing
│
├── src/                # 💻 Source code
│   └── server/
│       ├── app.py                  # Main FastAPI app (ASYNC ENDPOINTS ADDED!)
│       ├── async_request.py        # Async API models
│       └── job_manager.py          # Background job manager
│
└── [other files...]
```

## ⭐ What We Fixed & Added

### 1. **Fixed Streaming Issues**
- ✅ SSL certificate error with Tavily API
- ✅ Installed Python SSL certificates
- ✅ Updated tavily_search_api_wrapper.py to use certifi

### 2. **Created Async Background Job System**
- ✅ New endpoints:
  - `POST /api/research/async` - Start job
  - `GET /api/research/{job_id}/status` - Check progress
  - `GET /api/research/{job_id}/result` - Get final report
  - `DELETE /api/research/{job_id}` - Cancel job

- ✅ Status tracking:
  - pending → coordinating → planning → researching → reporting → completed

### 3. **Organized Documentation**
- ✅ Moved all guides to `education/`
- ✅ Created comprehensive README files
- ✅ Explained thread_id and how to get results easily

### 4. **Cleaned Up Project**
- ✅ Moved all test scripts to `tests/manual/`
- ✅ Root directory is clean
- ✅ Logical folder structure

## 🚀 Quick Start

### Easiest Way to Use DeerFlow:

```bash
# 1. Start server
uv run python -m uvicorn src.server.app:app --host 127.0.0.1 --port 8000

# 2. Run async test (in another terminal)
uv run python tests/manual/test_async_api.py
```

### Read This First:
1. `education/08-understanding-thread-id-and-results.md` - Understand how it works
2. `education/10-async-api-summary.md` - Quick API reference
3. `tests/manual/README.md` - All available tests

## 📊 API Comparison

| Feature | Async API | Streaming API |
|---------|-----------|---------------|
| Complexity | ⭐ Simple | ⭐⭐⭐ Complex |
| Getting results | One call | Filter 400+ events |
| Best for | Web/mobile apps | Real-time dashboards |
| **Recommended?** | ✅ YES | Only if you need streaming |

## 🎯 Key Concepts Explained

### Thread ID
- **What**: Conversation identifier (UUID)
- **When to use**: Continue conversations, remember context
- **Do you need it**: Optional for single questions
- **Details**: `education/08-understanding-thread-id-and-results.md`

### Getting Results
- **Easy way**: Use Async API - `GET /api/research/{job_id}/result`
- **Hard way**: Filter streaming events for reporter node
- **Why hard**: 400+ streaming events, need to filter
- **Details**: `education/08-understanding-thread-id-and-results.md`

### Parameters
All available in both APIs:
- `query` - Research question
- `max_step_num` - Number of steps (1-10)
- `search_provider` - tavily or firecrawl
- `report_style` - academic, news, etc.
- `auto_accepted_plan` - Skip plan approval
- Full list: `education/10-async-api-summary.md`

## 📚 Documentation Files

### Education Folder
- `08-understanding-thread-id-and-results.md` - **Start here!**
- `09-async-api-guide.md` - Complete guide with examples
- `10-async-api-summary.md` - Quick reference

### Tests Folder
- `test_async_api.py` - **Recommended test**
- `test_streaming_explained.py` - Learn streaming
- `test_get_final_answer.py` - Extract clean results
- `test-console.html` - Browser testing

## 🔧 What Changed in Code

### New Files
- `src/server/async_request.py` - Async API request/response models
- `src/server/job_manager.py` - Background job management

### Modified Files
- `src/server/app.py` - Added 4 new async endpoints + startup/shutdown hooks
- `src/tools/tavily_search/tavily_search_api_wrapper.py` - Fixed SSL with certifi

### No Breaking Changes
- All existing endpoints still work
- Streaming API unchanged
- Backward compatible

## 💡 Best Practices

1. **Use Async API** for most use cases
2. **Read education/08** to understand concepts
3. **Test with** `tests/manual/test_async_api.py`
4. **Only use streaming** if you need real-time updates
5. **Thread ID** is optional unless continuing conversations

## 🎓 Learning Path

```
1. Read: education/08-understanding-thread-id-and-results.md
2. Read: education/10-async-api-summary.md
3. Run:  tests/manual/test_async_api.py
4. Build: Your own integration using Async API
```

## ✅ Summary

**Problem**: Streaming was complex, results hard to get, project messy

**Solution**:
- ✅ Fixed SSL issues
- ✅ Created simple Async API
- ✅ Organized all docs in `education/`
- ✅ Moved all tests to `tests/manual/`
- ✅ Explained everything clearly

**Result**: Clean, organized, easy-to-use DeerFlow! 🎉
