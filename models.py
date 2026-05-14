import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._init_tables()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS expressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emotion TEXT NOT NULL DEFAULT 'neutral',
                situation TEXT NOT NULL,
                style TEXT NOT NULL,
                context_samples TEXT DEFAULT '[]',
                count INTEGER DEFAULT 1,
                checked INTEGER DEFAULT 0,
                rejected INTEGER DEFAULT 0,
                chat_id TEXT NOT NULL DEFAULT '',
                last_active_time REAL NOT NULL DEFAULT 0,
                created_at REAL NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_expressions_chat ON expressions(chat_id);
            CREATE INDEX IF NOT EXISTS idx_expressions_emotion ON expressions(emotion);
            CREATE INDEX IF NOT EXISTS idx_expressions_checked ON expressions(checked, rejected);

            CREATE TABLE IF NOT EXISTS jargons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL UNIQUE,
                meaning TEXT DEFAULT '',
                raw_contexts TEXT DEFAULT '[]',
                count INTEGER DEFAULT 1,
                chat_id TEXT NOT NULL DEFAULT '[]',
                is_global INTEGER DEFAULT 0,
                last_inference_count INTEGER DEFAULT 0,
                is_complete INTEGER DEFAULT 0,
                created_at REAL NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_jargons_content ON jargons(content);
            CREATE INDEX IF NOT EXISTS idx_jargons_is_global ON jargons(is_global);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_name_cache (
                chat_id TEXT PRIMARY KEY,
                chat_name TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS message_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                sender_name TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL,
                timestamp REAL NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_msg_buffer_chat ON message_buffer(chat_id);
        """)
        self._migrate_add_column(
            "message_buffer", "sender_name", "TEXT NOT NULL DEFAULT ''"
        )
        self._migrate_add_column("jargons", "rejected", "INTEGER DEFAULT 0")

    def _migrate_add_column(self, table: str, column: str, col_def: str):
        """安全添加列：如果列不存在则添加"""
        try:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set_setting(self, key: str, value: Any):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def cache_chat_name(self, chat_id: str, chat_name: str):
        """缓存 chat_id → 可读名称的映射"""
        import time

        if not chat_id or not chat_name:
            return
        existing = self.conn.execute(
            "SELECT chat_name FROM chat_name_cache WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
        if existing and existing["chat_name"] == chat_name:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO chat_name_cache (chat_id, chat_name, updated_at) VALUES (?, ?, ?)",
            (chat_id, chat_name, time.time()),
        )
        self.conn.commit()

    def get_chat_name(self, chat_id: str) -> str:
        """获取缓存的可读名称，未命中则返回空字符串"""
        row = self.conn.execute(
            "SELECT chat_name FROM chat_name_cache WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
        return row["chat_name"] if row else ""

    def get_chat_name_map(self, chat_ids: list[str]) -> dict[str, str]:
        """批量获取 chat_id → 名称映射"""
        if not chat_ids:
            return {}
        placeholders = ",".join("?" for _ in chat_ids)
        rows = self.conn.execute(
            f"SELECT chat_id, chat_name FROM chat_name_cache WHERE chat_id IN ({placeholders})",
            tuple(chat_ids),
        ).fetchall()
        return {r["chat_id"]: r["chat_name"] for r in rows}

    # ── Expression CRUD ──

    def add_expression(
        self,
        emotion: str,
        situation: str,
        style: str,
        context: str,
        chat_id: str,
        now: float | None = None,
    ) -> int:
        if now is None:
            now = time.time()
        cur = self.conn.execute(
            """INSERT INTO expressions (emotion, situation, style, context_samples, chat_id,
               last_active_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                emotion,
                situation,
                style,
                json.dumps([context], ensure_ascii=False),
                chat_id,
                now,
                now,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def find_similar_expression(
        self, situation: str, chat_id: str, threshold: float = 0.75
    ) -> tuple[dict | None, float]:
        from difflib import SequenceMatcher

        rows = self.conn.execute(
            "SELECT * FROM expressions WHERE chat_id=?", (chat_id,)
        ).fetchall()
        best = None
        best_sim = 0.0
        for row in rows:
            content_list = json.loads(row["context_samples"] or "[]")
            for existing in content_list:
                sim = SequenceMatcher(None, situation, existing).ratio()
                if sim >= threshold and sim > best_sim:
                    best_sim = sim
                    best = dict(row)
        return best, best_sim

    def update_expression_count(self, expr_id: int, new_situation: str, now: float):
        row = self.conn.execute(
            "SELECT * FROM expressions WHERE id=?", (expr_id,)
        ).fetchone()
        if not row:
            return
        content_list = json.loads(row["context_samples"] or "[]")
        content_list.append(new_situation)
        self.conn.execute(
            "UPDATE expressions SET context_samples=?, count=count+1, checked=0, last_active_time=? WHERE id=?",
            (json.dumps(content_list, ensure_ascii=False), now, expr_id),
        )
        self.conn.commit()

    def get_expression_by_id(self, expr_id: int) -> dict | None:
        """获取单条表达方式"""
        row = self.conn.execute(
            "SELECT * FROM expressions WHERE id=?", (expr_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_expressions(
        self,
        chat_id: str | None = None,
        emotion: str | None = None,
        page: int = 1,
        page_size: int = 20,
        checked_only: bool = False,
        exclude_rejected: bool = False,
        status: str = "",
    ) -> tuple[list[dict], int]:
        conditions = []
        params = []
        if chat_id:
            conditions.append("chat_id=?")
            params.append(chat_id)
        if emotion and emotion != "all":
            conditions.append("emotion=?")
            params.append(emotion)
        if status == "pending":
            conditions.append("checked=0 AND rejected=0")
        elif status == "approved":
            conditions.append("checked=1 AND rejected=0")
        elif status == "rejected":
            conditions.append("rejected=1")
        elif checked_only:
            conditions.append("checked=1 AND rejected=0")
        elif exclude_rejected:
            conditions.append("rejected=0")
        where = " AND ".join(conditions) if conditions else "1"
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM expressions WHERE {where}", params
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = self.conn.execute(
            f"SELECT * FROM expressions WHERE {where} ORDER BY count DESC, last_active_time DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        return [dict(r) for r in rows], total

    def get_expressions_by_emotion(
        self, chat_id: str, emotion: str, limit: int = 10
    ) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM expressions WHERE chat_id=? AND emotion=? AND rejected=0 ORDER BY count DESC LIMIT ?",
            (chat_id, emotion, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_random_expressions(
        self, chat_id: str, limit: int = 10, min_count: int = 1
    ) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM expressions WHERE chat_id=? AND rejected=0 AND count>=? ORDER BY RANDOM() LIMIT ?",
            (chat_id, min_count, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def check_expression(self, expr_id: int, checked: bool, rejected: bool):
        self.conn.execute(
            "UPDATE expressions SET checked=?, rejected=? WHERE id=?",
            (1 if checked else 0, 1 if rejected else 0, expr_id),
        )
        self.conn.commit()

    def update_expression(self, expr_id: int, **kwargs):
        sets = []
        params = []
        for k, v in kwargs.items():
            sets.append(f"{k}=?")
            params.append(v)
        if sets:
            params.append(expr_id)
            self.conn.execute(
                f"UPDATE expressions SET {', '.join(sets)} WHERE id=?", params
            )
            self.conn.commit()

    def delete_expression(self, expr_id: int):
        self.conn.execute("DELETE FROM expressions WHERE id=?", (expr_id,))
        self.conn.commit()

    # ── Jargon CRUD ──

    def add_or_update_jargon(
        self, content: str, raw_context: str, chat_id: str, is_global: bool = False
    ) -> bool:
        existing = self.conn.execute(
            "SELECT * FROM jargons WHERE content=?", (content,)
        ).fetchone()
        if existing:
            row = dict(existing)
            rc_list = json.loads(row["raw_contexts"] or "[]")
            if raw_context not in rc_list:
                rc_list.append(raw_context)
            chat_id_list = json.loads(row["chat_id"] or "[]")
            found = False
            for item in chat_id_list:
                if isinstance(item, list) and len(item) >= 1 and item[0] == chat_id:
                    item[1] = (item[1] if isinstance(item[1], (int, float)) else 0) + 1
                    found = True
                    break
            if not found:
                chat_id_list.append([chat_id, 1])
            self.conn.execute(
                "UPDATE jargons SET count=count+1, raw_contexts=?, chat_id=?, is_global=? WHERE id=?",
                (
                    json.dumps(rc_list, ensure_ascii=False),
                    json.dumps(chat_id_list, ensure_ascii=False),
                    1 if is_global else row["is_global"],
                    row["id"],
                ),
            )
            self.conn.commit()
            return True
        now = time.time()
        chat_id_list = json.dumps([[chat_id, 1]], ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO jargons (content, raw_contexts, chat_id, is_global, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                content,
                json.dumps([raw_context], ensure_ascii=False),
                chat_id_list,
                1 if is_global else 0,
                now,
            ),
        )
        self.conn.commit()
        return False

    def update_jargon_meaning(
        self, jargon_id: int, meaning: str, is_jargon: bool = False
    ):
        self.conn.execute(
            "UPDATE jargons SET meaning=?, is_complete=? WHERE id=?",
            (meaning, 1 if not is_jargon else 0, jargon_id),
        )
        self.conn.commit()

    def get_jargons(
        self, chat_id: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[dict], int]:
        total = 0
        if chat_id:
            rows = self.conn.execute(
                "SELECT * FROM jargons ORDER BY count DESC", ()
            ).fetchall()
            filtered = []
            for r in rows:
                d = dict(r)
                cl = json.loads(d["chat_id"] or "[]")
                if any(isinstance(i, list) and i[0] == chat_id for i in cl):
                    filtered.append(d)
            total = len(filtered)
            offset = (page - 1) * page_size
            return filtered[offset : offset + page_size], total
        else:
            total = self.conn.execute("SELECT COUNT(*) FROM jargons").fetchone()[0]
            offset = (page - 1) * page_size
            rows = self.conn.execute(
                "SELECT * FROM jargons ORDER BY count DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
            return [dict(r) for r in rows], total

    def search_jargons(
        self,
        keyword: str,
        chat_id: str | None = None,
        fuzzy: bool = True,
        limit: int = 10,
    ) -> list[dict]:
        if fuzzy:
            rows = self.conn.execute(
                "SELECT * FROM jargons WHERE content LIKE ? AND meaning != '' AND meaning IS NOT NULL ORDER BY count DESC",
                (f"%{keyword}%",),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM jargons WHERE content=? AND meaning != '' AND meaning IS NOT NULL ORDER BY count DESC",
                (keyword,),
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if chat_id:
                cl = json.loads(d["chat_id"] or "[]")
                if d["is_global"] or any(
                    isinstance(i, list) and i[0] == chat_id for i in cl
                ):
                    results.append(d)
            else:
                results.append(d)
            if len(results) >= limit:
                break
        return results

    def match_jargons_in_text(
        self, text: str, chat_id: str | None = None
    ) -> list[dict]:
        import re

        if not text:
            return []
        rows = self.conn.execute(
            "SELECT * FROM jargons WHERE meaning != '' AND meaning IS NOT NULL ORDER BY count DESC",
        ).fetchall()
        matched = {}
        for r in rows:
            d = dict(r)
            content = d["content"]
            if not content or not content.strip():
                continue
            if chat_id:
                cl = json.loads(d["chat_id"] or "[]")
                if not d["is_global"] and not any(
                    isinstance(i, list) and i[0] == chat_id for i in cl
                ):
                    continue
            pattern = re.escape(content)
            if not re.search(r"[\u4e00-\u9fff]", content):
                pattern = r"\b" + pattern + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                if content not in matched:
                    matched[content] = d
        return list(matched.values())

    def get_jargon_by_content(self, content: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM jargons WHERE content=?", (content,)
        ).fetchone()
        return dict(row) if row else None

    def delete_jargon(self, jargon_id: int):
        self.conn.execute("DELETE FROM jargons WHERE id=?", (jargon_id,))
        self.conn.commit()

    # ── Statistics ──

    def get_statistics(self) -> dict:
        expr_count = self.conn.execute("SELECT COUNT(*) FROM expressions").fetchone()[0]
        expr_checked = self.conn.execute(
            "SELECT COUNT(*) FROM expressions WHERE checked=1"
        ).fetchone()[0]
        expr_rejected = self.conn.execute(
            "SELECT COUNT(*) FROM expressions WHERE rejected=1"
        ).fetchone()[0]
        jargon_count = self.conn.execute("SELECT COUNT(*) FROM jargons").fetchone()[0]
        jargon_with_meaning = self.conn.execute(
            "SELECT COUNT(*) FROM jargons WHERE meaning != '' AND meaning IS NOT NULL"
        ).fetchone()[0]
        chat_groups = self.conn.execute(
            "SELECT DISTINCT chat_id FROM expressions WHERE chat_id != ''"
        ).fetchall()
        emotions = self.conn.execute(
            "SELECT emotion, COUNT(*) as cnt FROM expressions GROUP BY emotion ORDER BY cnt DESC"
        ).fetchall()
        return {
            "total_expressions": expr_count,
            "checked_expressions": expr_checked,
            "rejected_expressions": expr_rejected,
            "total_jargons": jargon_count,
            "jargons_with_meaning": jargon_with_meaning,
            "chat_group_count": len(chat_groups),
            "emotion_distribution": {r["emotion"]: r["cnt"] for r in emotions},
        }

    def get_chat_groups(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT chat_id FROM expressions WHERE chat_id != ''"
        ).fetchall()
        return [r["chat_id"] for r in rows]

    def get_known_chats(self) -> list[dict]:
        """从 chat_name_cache 获取所有已知会话，按更新时间倒序"""
        rows = self.conn.execute(
            "SELECT chat_id, chat_name, updated_at FROM chat_name_cache ORDER BY updated_at DESC"
        ).fetchall()
        return [{"chat_id": r["chat_id"], "chat_name": r["chat_name"]} for r in rows]

    # ── Message buffer ──

    def save_buffered_messages(self, chat_id: str, messages: list[dict]):
        self.conn.execute("DELETE FROM message_buffer WHERE chat_id=?", (chat_id,))
        for msg in messages:
            self.conn.execute(
                "INSERT INTO message_buffer (chat_id, role, sender_name, text, timestamp) VALUES (?, ?, ?, ?, ?)",
                (
                    chat_id,
                    msg.get("role", ""),
                    msg.get("sender_name", ""),
                    msg.get("text", ""),
                    msg.get("time", 0.0),
                ),
            )
        self.conn.commit()

    def load_buffered_messages(self, chat_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, sender_name, text, timestamp FROM message_buffer WHERE chat_id=? ORDER BY timestamp",
            (chat_id,),
        ).fetchall()
        return [
            {
                "role": r["role"],
                "sender_name": r["sender_name"],
                "text": r["text"],
                "time": r["timestamp"],
            }
            for r in rows
        ]

    def get_all_buffered_chat_ids(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT chat_id FROM message_buffer"
        ).fetchall()
        return [r["chat_id"] for r in rows]

    def clear_buffered_messages(self, chat_id: str):
        self.conn.execute("DELETE FROM message_buffer WHERE chat_id=?", (chat_id,))
        self.conn.commit()


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        db_dir = (
            Path(get_astrbot_data_path()) / "plugins" / "astrbot_plugin_style_learner"
        )
        _db = Database(db_dir / "data.db")
        _db.connect()
    return _db
