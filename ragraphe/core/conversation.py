"""
對話式入口：AI 透過問答收集上下文，路徑拓樸閉合後生成節點路徑

兩個階段：
  1. 接線：對話收集上下文，AI 邊問邊評估是否已足夠生成路徑
  2. 降電阻：路徑生成後，逐節點引導用戶補充內容
"""
import re
import uuid
from ragraphe.llm.ollama_client import chat
from ragraphe.core.path_planner import plan_path
from ragraphe.db.store import init_db

MAX_TURNS = 3  # 最多問幾輪就生成路徑

COLLECT_SYSTEM = """你是路徑規劃助手，負責收集使用者的目標背景資訊。
規則：
- 只輸出一個問題，以問號結尾
- 不要問候語，不要說「太好了」「很棒」等廢話
- 不要解釋，直接問
- 使用繁體中文

根據目前已知資訊，問最缺少的那一個問題。"""


def _extract_question(text: str) -> str:
    """從模型回覆中萃取第一個乾淨問句"""
    QUESTION_WORDS = ("what", "how", "when", "where", "who", "have", "has",
                      "is", "are", "do", "does", "can", "will", "would",
                      "你", "請問", "是否", "有沒有", "幾", "哪", "什麼", "為什麼", "怎")
    SKIP_PREFIXES = (
        "that's", "this is", "great", "excellent", "wonderful", "amazing",
        "exciting", "perfect", "fantastic", "sure", "of course", "absolutely",
        "certainly", "thank", "i understand", "i see", "sounds",
        "那", "好的", "沒問題", "當然", "明白", "了解", "很好", "太好了",
    )

    candidates = []
    for line in text.split('\n'):
        line = line.strip().lstrip('*#-–•1234567890. \n')
        if not line:
            continue
        if line.endswith('?') or line.endswith('？'):
            clean = re.sub(r'\*+', '', line).strip()
            if len(clean) < 10:
                continue
            # 去掉 "Label: Question?" 前綴
            if ': ' in clean and not clean.lower().startswith(QUESTION_WORDS):
                clean = clean.split(': ', 1)[1].strip()
            low = clean.lower()
            if any(low.startswith(w) for w in QUESTION_WORDS):
                return clean
            candidates.append(clean)

    if candidates:
        return candidates[0]

    # fallback：跳過問候語，取第一個有實質內容的行
    for line in text.split('\n'):
        line = line.strip().lstrip('*#- ')
        if line and not any(line.lower().startswith(p) for p in SKIP_PREFIXES):
            return line
    return text.strip()


class ConversationSession:
    def __init__(self, user_id: str = "default", domain: str = "general"):
        self.user_id = user_id
        self.domain = domain
        self.goal = ""
        self.turns = 0
        self.history = []  # [{"role": "user/assistant", "content": "..."}]
        self.session_id = str(uuid.uuid4())[:8]
        init_db()

    def _next_question(self) -> str:
        response = chat(system=COLLECT_SYSTEM, messages=self.history)
        return _extract_question(response)

    def _build_context(self) -> str:
        """直接串接用戶答案作為上下文（不走 LLM 摘要，格式不穩定）"""
        user_answers = [m["content"] for m in self.history if m["role"] == "user"]
        extra = "; ".join(user_answers[1:]) if len(user_answers) > 1 else ""
        return f"{extra}; goal: {self.goal}" if extra else self.goal

    def start(self, goal: str, missing: str = "") -> str:
        """開始對話，回傳第一個問題"""
        self.goal = goal
        content = goal
        if missing:
            content = f"目標：{goal}\n目前骨架缺少的資訊：{missing}"
        self.history.append({"role": "user", "content": content})
        question = self._next_question()
        self.history.append({"role": "assistant", "content": question})
        self.turns += 1
        return question

    def reply(self, answer: str) -> str | None:
        """用戶回答後繼續對話。回傳下一個問題，或 None 表示已收集足夠。"""
        self.history.append({"role": "user", "content": answer})
        if self.turns >= MAX_TURNS:
            return None
        question = self._next_question()
        self.history.append({"role": "assistant", "content": question})
        self.turns += 1
        return question

    def generate_path(self, user_states: dict = None) -> dict:
        """收集完畢後生成路徑"""
        context = self._build_context()
        print(f"\n📡 上下文：{context}")
        print("🔄 生成路徑中...\n")
        return plan_path(
            goal=self.goal,
            context=context,
            user_id=self.user_id,
            domain=self.domain,
            user_states=user_states or {},
        )


def run_interactive(user_id: str = "default", domain: str = "general"):
    """互動式 CLI 對話入口"""
    print("=" * 50)
    print("  Ragraphe")
    print("=" * 50)

    goal = input("Goal / 目標 > ").strip()
    if not goal or goal.lower() == "quit":
        return

    session = ConversationSession(user_id=user_id, domain=domain)
    question = session.start(goal)

    while question:
        print(f"\nAI: {question}")
        answer = input("> ").strip()
        if answer.lower() == "quit":
            return
        question = session.reply(answer)

    return session.generate_path()


if __name__ == "__main__":
    run_interactive(user_id="user_001", domain="travel")
