import json
import uuid
import cmd
from datetime import datetime
from pathlib import Path

class Task:
    def __init__(self, name, importance, urgency=None, deadline=None, created_at=None, task_id=None):
        self.id = task_id or str(uuid.uuid4())[:6]
        self.name = name
        self.importance = max(1, min(10, float(importance))) # 1-10
        
        self.created_at = datetime.fromisoformat(created_at) if created_at else datetime.now()
        self.deadline = datetime.fromisoformat(deadline) if deadline else None
        
        # 若有設定 deadline，系統自動轉換為緊急度；否則使用手動輸入的緊急度
        if self.deadline:
            self.urgency = self._calculate_urgency()
        else:
            self.urgency = max(1, min(10, float(urgency or 1)))

    def _calculate_urgency(self):
        """將 Deadline 線性轉換為緊急度 (1-10)"""
        if not self.deadline:
            return 1.0
        now = datetime.now()
        if self.deadline <= now:
            return 10.0 # 已經過期，緊急度拉滿
            
        hours_left = (self.deadline - now).total_seconds() / 3600
        # 假設大於 14 天 (336小時) 為最低緊急度 1，24小時內為最高 10
        if hours_left >= 336:
            return 1.0
        elif hours_left <= 24:
            return 10.0
        else:
            # 線性轉換
            return 10.0 - ((hours_left - 24) * (9.0 / 312))

    def get_score(self):
        """
        計算綜合權重：
        基礎分數 = (重要性 * 1.5) + 緊急度
        老化機制 (Aging) = 任務每存活 1 天，分數增加 0.5 (防止 Starvation)
        """
        # 動態更新因 deadline 產生的 urgency
        if self.deadline:
            self.urgency = self._calculate_urgency()
            
        base_score = (self.importance * 1.5) + self.urgency
        days_alive = (datetime.now() - self.created_at).total_seconds() / 86400
        aging_bonus = days_alive * 0.5
        
        return base_score + aging_bonus

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "importance": self.importance,
            "urgency": self.urgency,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat()
        }

class MaxHeap:
    def __init__(self):
        self.heap = []
        self.pos_map = {} # Hash Table: task_id -> index 達成 O(1) 尋址

    def peek_max(self):
        """O(1) 取得當前最高優先任務但不移除"""
        return self.heap[0] if self.heap else None

    def _swap(self, i, j):
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
        self.pos_map[self.heap[i].id] = i
        self.pos_map[self.heap[j].id] = j

    def _sift_up(self, i):
        parent = (i - 1) // 2
        while i > 0 and self.heap[i].get_score() > self.heap[parent].get_score():
            self._swap(i, parent)
            i = parent
            parent = (i - 1) // 2

    def _sift_down(self, i):
        n = len(self.heap)
        while True:
            largest = i
            left = 2 * i + 1
            right = 2 * i + 2

            if left < n and self.heap[left].get_score() > self.heap[largest].get_score():
                largest = left
            if right < n and self.heap[right].get_score() > self.heap[largest].get_score():
                largest = right

            if largest != i:
                self._swap(i, largest)
                i = largest
            else:
                break

    def insert(self, task):
        """O(log N) 插入新任務"""
        self.heap.append(task)
        idx = len(self.heap) - 1
        self.pos_map[task.id] = idx
        self._sift_up(idx)

    def extract_max(self):
        """O(1) 提取並 O(log N) 重構"""
        if not self.heap:
            return None
        max_task = self.heap[0]
        last_task = self.heap.pop()
        del self.pos_map[max_task.id]
        
        if self.heap:
            self.heap[0] = last_task
            self.pos_map[last_task.id] = 0
            self._sift_down(0)
            
        return max_task

    def remove_by_id(self, task_id):
        """O(log N) 依任務 ID 刪除指定任務"""
        idx = self.pos_map.get(task_id)
        if idx is None:
            return None

        removed_task = self.heap[idx]
        last_idx = len(self.heap) - 1

        if idx == last_idx:
            self.heap.pop()
            del self.pos_map[removed_task.id]
            return removed_task

        last_task = self.heap.pop()
        del self.pos_map[removed_task.id]
        self.heap[idx] = last_task
        self.pos_map[last_task.id] = idx

        parent = (idx - 1) // 2
        if idx > 0 and self.heap[idx].get_score() > self.heap[parent].get_score():
            self._sift_up(idx)
        else:
            self._sift_down(idx)

        return removed_task

    def refresh(self):
        """
        因時間推移導致 Aging 與 Deadline 分數變動，觸發全域重構。
        此為 O(N) 操作，僅在使用者要求印出最新列表時觸發。
        """
        n = len(self.heap)
        for i in range(n // 2 - 1, -1, -1):
            self._sift_down(i)

class EisenhowerEngineCLI(cmd.Cmd):
    intro = '歡迎使用艾森豪矩陣任務優先權決策引擎 (輸入 help 查看指令)'
    prompt = '(Engine) > '

    def __init__(self):
        super().__init__()
        self.heap = MaxHeap()
        self.data_file = Path(__file__).with_name('tasks_data.json')
        self.current_task_id = None

    def do_add(self, arg):
        """
        新增任務
        用法: add <任務名稱> <重要性1-10> <緊急度1-10或Deadline YYYY-MM-DD>
        範例1: add 寫專題報告 9 8
        範例2: add 繳交水電費 5 2024-06-30
        """
        args = arg.split()
        if len(args) < 3:
            print("❌ 參數錯誤。用法: add <名稱> <重要度> <緊急度/日期>")
            return
            
        name = args[0]
        try:
            importance = float(args[1])
            urgency_or_date = args[2]
            
            if "-" in urgency_or_date:
                # 判斷為日期字串
                task = Task(name=name, importance=importance, deadline=urgency_or_date)
            else:
                # 判斷為直接評分
                task = Task(name=name, importance=importance, urgency=float(urgency_or_date))
                
            self.heap.insert(task)
            print(f"✅ 任務 [{task.name}] 已加入，初始權重分數: {task.get_score():.2f}")
        except ValueError:
            print("❌ 日期格式請使用 YYYY-MM-DD，或確保重要度/緊急度為數字。")

    def do_next(self, arg):
        """O(1) 查看當下最高優先權任務（不刪除）"""
        # 查看前先更新一次老化狀態以確保精準
        self.heap.refresh()
        task = self.heap.peek_max()
        if not task:
            self.current_task_id = None
            print("🎉 當前無待辦任務！")
        else:
            self.current_task_id = task.id
            print(f"🔥 [最高優先執行] {task.name} (ID: {task.id}) | 綜合權重: {task.get_score():.2f}")
            print("✅ 完成後請輸入 done 來刪除這個任務。")

    def do_done(self, arg):
        """完成目前任務並刪除（需先使用 next 指定）"""
        if not self.heap.heap:
            self.current_task_id = None
            print("🎉 當前無待辦任務！")
            return

        if not self.current_task_id:
            print("⚠️ 尚未指定目前任務，請先輸入 next。")
            return

        removed = self.heap.remove_by_id(self.current_task_id)
        if not removed:
            self.current_task_id = None
            print("⚠️ 目前任務不存在，請重新輸入 next。")
            return

        print(f"✅ 已完成並刪除任務：{removed.name} (ID: {removed.id})")
        self.current_task_id = None

    def do_list(self, arg):
        """列出當前所有任務 (會先觸發權重更新)"""
        if not self.heap.heap:
            print("📭 清單為空。")
            return
            
        self.heap.refresh()
        # 暫時複製並排序以利顯示，不影響底層結構
        sorted_tasks = sorted(self.heap.heap, key=lambda x: x.get_score(), reverse=True)
        
        print(f"{'ID':<8} | {'任務名稱':<15} | {'重要度':<6} | {'緊急度':<6} | {'綜合權重':<8}")
        print("-" * 55)
        for t in sorted_tasks:
            urg_str = f"{t.urgency:.1f}"
            if t.deadline:
                urg_str += "(DL)"
            print(f"{t.id:<8} | {t.name:<15} | {t.importance:<6.1f} | {urg_str:<6} | {t.get_score():<8.2f}")

    def do_save(self, arg):
        """資料持久化：將狀態匯出為 JSON"""
        data = [t.to_dict() for t in self.heap.heap]
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 已將 {len(data)} 筆任務儲存至 {self.data_file.name}")

    def do_load(self, arg):
        """匯入 JSON 資料"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.heap = MaxHeap() # 重置
                for d in data:
                    t = Task(
                        name=d['name'], 
                        importance=d['importance'], 
                        urgency=d['urgency'], 
                        deadline=d['deadline'][:10] if d['deadline'] else None,
                        created_at=d['created_at'],
                        task_id=d['id']
                    )
                    self.heap.insert(t)
            print(f"📂 成功載入 {len(data)} 筆任務！")
        except FileNotFoundError:
            print("❌ 找不到存檔檔案。")

    def do_exit(self, arg):
        """離開系統"""
        self.do_save(arg)
        print("👋 系統關閉，再見！")
        return True

if __name__ == '__main__':
    EisenhowerEngineCLI().cmdloop()