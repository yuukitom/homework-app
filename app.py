import sqlite3
from datetime import date, datetime
import time
import streamlit as st

DB_PATH = "homework.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# データベース初期化
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )
    """
    )

    # 宿題テーブル（進捗%と完了フラグを持つ）
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        due_date TEXT NOT NULL,              -- 'YYYY-MM-DD'
        progress INTEGER NOT NULL DEFAULT 0, -- 0-100
        is_completed INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(child_id) REFERENCES children(id)
    )
    """
    )

    # 設定テーブル（ご褒美の閾値など）
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
        )
    """
    )

    cur.execute("SELECT COUNT(*) FROM children")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO children(name) VALUES (?)", ("YUMA",))

    # 初期値：ご褒美に必要な⭐数 = 10（無ければ入れる）
    cur.execute("SELECT value FROM settings WHERE key='reward_threshold'")
    if cur.fetchone() is None:
        cur.execute("INSERT INTO settings(key, value) VALUES (?, ?)", ("reward_threshold", "10"))

    conn.commit()
    conn.close()


# 子ども一覧を取得
def get_children():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM children ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


# 宿題を追加
def add_task(child_id: int, title: str, due_date_str: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks(child_id, title, due_date, progress, is_completed) VALUES (?, ?, ?, 0, 0)",
        (child_id, title, due_date_str),
    )
    conn.commit()
    conn.close()


def list_tasks(child_id: int):
    """宿題一覧をDBから取る（期限が近い順、同じなら新しい順）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, due_date, progress, is_completed
        FROM tasks
        WHERE child_id=?
        ORDER BY due_date ASC, id DESC
    """,
        (child_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def update_progress(task_id: int, progress: int):
    """宿題の進捗を更新"""

    """指定した宿題の進捗(0-100)を更新する"""
    progress = max(0, min(100, int(progress)))  # 念のため範囲を固定

    # 100%なら完了扱い
    is_completed = 1 if progress >= 100 else 0

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tasks
        SET progress=?, is_completed=?
        WHERE id=?
    """,
        (progress, is_completed, task_id),
    )
    conn.commit()
    conn.close()


# ご褒美の★のカウント
def count_stars(child_id: int) -> int:
    """完了した宿題の数を数える（完了数＝⭐）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM tasks WHERE child_id=? AND is_completed=1",
        (child_id,),
    )
    stars = cur.fetchone()[0]
    conn.close()
    return stars


# 設定の取得・保存
def get_setting(key: str, default: str) -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """,
        (key, value),
    )
    conn.commit()
    conn.close()


def delete_task(task_id: int):
    """宿題を1件削除"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


@st.dialog("削除の確認")
def confirm_delete_dialog():
    tid = st.session_state.delete_target_id

    st.write("本当にこの宿題を削除しますか？（取り消し不可）")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("はい（削除）", type="primary"):
            delete_task(tid)
            st.session_state.delete_target_id = None
            st.session_state.open_delete_dialog = False
            st.rerun()

    with col2:
        if st.button("いいえ（キャンセル）"):
            st.session_state.delete_target_id = None
            st.session_state.open_delete_dialog = False
            st.rerun()


def reset_tasks(child_id: int):
    """子ども単位で宿題を全削除（リセット）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE child_id=?", (child_id,))
    conn.commit()
    conn.close()


def days_until(due_date_str: str) -> int:
    """期限(YYYY-MM-DD)までの残り日数。過ぎてたらマイナス。"""
    due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    return (due - date.today()).days


# -----------------
# UI（画面）
# -----------------
st.set_page_config(page_title="宿題管理", page_icon="📚")
st.title("📚 宿題管理アプリ")

init_db()

# セッションステート（削除）初期化
if "delete_target_id" not in st.session_state:
    st.session_state.delete_target_id = None

if "open_delete_dialog" not in st.session_state:
    st.session_state.open_delete_dialog = False

# 子ども選択（将来、複数にできる設計）
children = get_children()
child_map = {name: cid for cid, name in children}  # {子ども名: 子どもID}
child_name = st.selectbox("子どもを選択", list(child_map.keys()))
child_id = child_map[child_name]

tabs = st.tabs(["✅ 今日の進捗", "➕ 宿題を追加", "⚙️ 設定"])

with tabs[0]:

    # ダイアログを開く
    if st.session_state.open_delete_dialog:
        # delete_target_id が入っている前提
        confirm_delete_dialog()

    # ⭐表示
    REWARD_THRESHOLD = int(get_setting("reward_threshold", "10"))
    stars = count_stars(child_id)

    st.subheader("⭐ ご褒美までの進捗")
    st.write(f"いまの⭐**{stars}** / ご褒美まで **{REWARD_THRESHOLD}**")

    # progressは0.0〜1.0
    st.progress(min(1.0, stars / REWARD_THRESHOLD))

    if stars >= REWARD_THRESHOLD:
        st.success("ご褒美ゲット！おめでとう🎉")

    st.divider()  # 区切り線

    # 宿題一覧表示
    st.subheader("📋 宿題一覧（DBから取得）")
    tasks = list_tasks(child_id)

    if not tasks:
        st.info("宿題がまだありません。上で追加してね。")
    else:
        for tid, ttitle, due_date_str, progress, is_completed in tasks:
            status = "✅完了" if is_completed else "🟡進行中"
            remain = days_until(due_date_str)  # 期限までの日数

            # タイトルと期限表示
            st.write(f"**{ttitle}**  ({status})")

            # 期限メッセージ（完了済みは控えめ表示）
            if is_completed:
                due_msg = f"期限: {due_date_str}（完了済み）"
            else:
                if remain < 0:
                    due_msg = f"⚠️ 期限切れ：{due_date_str}（{abs(remain)}日超過）"
                elif remain == 0:
                    due_msg = f"🚨 今日が期限：{due_date_str}"
                elif remain <= 2:
                    due_msg = f"⚠️ 期限まであと{remain}日：{due_date_str}"
                else:
                    due_msg = f"期限: {due_date_str}（あと{remain}日）"

            # 期限の強調表示（状況に応じて色を変える）
            if (not is_completed) and (remain < 0):
                st.error(due_msg)
            elif (not is_completed) and (remain == 0):
                st.warning(due_msg)
            elif (not is_completed) and (remain <= 2):
                st.warning(due_msg)
            else:
                st.caption(due_msg)

            # 進捗バー
            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                st.progress(progress / 100)

            with col2:
                # 進捗%表示
                new_progress = st.slider("進捗(%)", 0, 100, int(progress), step=10, key=f"p_{tid}")

                # 進捗更新ボタン
                msg_area_progress = st.empty()

                if st.button("更新", key=f"u_{tid}"):
                    update_progress(tid, new_progress)

                    # 成功メッセージ表示
                    msg_area_progress.success("進捗を更新したよ！")
                    time.sleep(1)
                    msg_area_progress.empty()

                    # 画面再実行して進捗バーを更新
                    st.rerun()

            with col3:
                if st.button("🗑️", key=f"d_{tid}"):
                    st.session_state.delete_target_id = tid
                    st.session_state.open_delete_dialog = True
                    st.rerun()

            # # 削除ボタン
            # msg_area_delete = st.empty()

            # if st.button("🗑️", key=f"d_{tid}"):
            #     delete_task(tid)

            #     # 成功メッセージ表示
            #     msg_area_delete.success("宿題を削除したよ！")
            #     time.sleep(1)
            #     msg_area_delete.empty()

            #     # 画面再実行して一覧を更新
            #     st.rerun()

            st.write("---")

with tabs[1]:
    # 宿題追加フォーム
    st.subheader("➕ 宿題を追加")

    with st.form(key="add_task_form", clear_on_submit=True):
        title = st.text_input("宿題名（例：算数ドリル）")
        due = st.date_input("期限", value=date.today())
        submitted = st.form_submit_button("追加する")

        # メッセージ表示用の空箱
        msg_area_add = st.empty()

        # 宿題追加ボタン
        if submitted:
            # 入力チェック
            if not title.strip():
                st.error("宿題名を入力してね")
            else:
                add_task(child_id, title.strip(), str(due))
                st.session_state.just_added = True  # 次の描画で出す

                # 成功メッセージ表示
                msg_area_add.success("追加したよ！")

                # 1秒待つ
                time.sleep(1)

                # メッセージを消す（フェードアウト風）
                msg_area_add.empty()

                # 追加直後に画面を再実行して一覧を更新
                st.rerun()

with tabs[2]:
    # ご褒美の⭐数設定
    st.subheader("⚙️ 設定：ご褒美の⭐数")
    threshold_now = int(get_setting("reward_threshold", "10"))

    new_threshold = st.number_input("ご褒美に必要な⭐数", min_value=1, max_value=999, value=threshold_now, step=1)

    # メッセージ表示枠
    msg_area_setting = st.empty()

    if st.button("設定を保存"):
        set_setting("reward_threshold", str(int(new_threshold)))

        # 成功メッセージ表示
        msg_area_setting.success("保存しました！")
        time.sleep(1)
        msg_area_setting.empty()

        # 画面再実行して成功メッセージを消す
        st.rerun()

    st.divider()

    # 宿題リセットボタン
    st.subheader("⚠️ 注意：宿題をリセット（全削除）")

    with st.form("reset_form", clear_on_submit=True):
        confirm = st.checkbox("本当に削除します（取り消し不可）")
        do_reset = st.form_submit_button("すべての宿題を削除")

    msg_area_reset = st.empty()

    if do_reset:
        if not confirm:
            st.error("チェックボックスをオンにしてね")
        else:
            reset_tasks(child_id)

            # 成功メッセージ表示
            msg_area_reset.success("宿題を全て削除したよ！")
            time.sleep(1)
            msg_area_reset.empty()

            # 画面再実行して一覧を更新
            st.rerun()
