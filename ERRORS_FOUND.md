# Code Review: Errors Found & Fixed

## 1. CRITICAL: Unused Import (backend/main.py)

**Line:** 1  
**Severity:** Critical  

```python
# Before
from urllib import response

# After
# (removed entirely)
```

**Explanation:** The `response` symbol from `urllib` was imported but never used anywhere in the file. This is dead code that adds unnecessary confusion and could shadow other variables named `response`.

---

## 2. CRITICAL: Invalid OpenAI Model Name (backend/main.py)

**Line:** 261  
**Severity:** Critical — causes runtime API error  

```python
# Before
model="gpt-5-nano",

# After
model="gpt-4o-mini",
```

**Explanation:** `gpt-5-nano` is not a valid OpenAI model identifier. Every call to the AI chat endpoint would fail with an API error, making the core feature completely non-functional. Replaced with `gpt-4o-mini`, a valid and cost-effective model.

---

## 3. BUG: Bare `except:` Clauses (backend/main.py)

**Lines:** 308, 328  
**Severity:** Bug — silently swallows all exceptions  

```python
# Before (line 308)
except:
    pass

# After
except (json.JSONDecodeError, ValueError):
    pass
```

```python
# Before (line 328)
except:
    continue

# After
except (json.JSONDecodeError, ValueError):
    continue
```

**Explanation:** Bare `except:` catches every exception including `KeyboardInterrupt`, `SystemExit`, and `MemoryError`. This hides real bugs and makes debugging impossible. Narrowed to only catch the expected JSON parsing errors.

---

## 4. BUG: Deprecated `onKeyPress` (frontend/components/ChatWindow.tsx)

**Line:** 169  
**Severity:** Bug — deprecated React event handler  

```tsx
// Before
onKeyPress={handleKeyPress}

// After
onKeyDown={handleKeyPress}
```

**Explanation:** `onKeyPress` is deprecated in modern React and does not fire for all keys consistently across browsers. `onKeyDown` is the correct replacement and provides reliable keyboard event handling.

---

## 5. DEPRECATION: `declarative_base()` (backend/database.py)

**Lines:** 2, 56  
**Severity:** Deprecation warning in SQLAlchemy 2.0+  

```python
# Before
from sqlalchemy.ext.declarative import declarative_base
# ...
Base = declarative_base()

# After
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase
# ...
class Base(DeclarativeBase):
    pass
```

**Explanation:** `declarative_base()` from `sqlalchemy.ext.declarative` has been deprecated since SQLAlchemy 2.0. The modern approach is to subclass `DeclarativeBase` from `sqlalchemy.orm`.