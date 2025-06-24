import os
import requests
import google.generativeai as genai
from dotenv import load_dotenv

def get_latest_pr_number(owner: str, repo: str, token: str) -> int | None:
    """
    從 GitHub 獲取指定倉庫最新的 Pull Request 編號。

    Args:
        owner: 倉庫擁有者。
        repo: 倉庫名稱。
        token: GitHub Personal Access Token。

    Returns:
        最新的 PR 編號，如果沒有找到或發生錯誤則返回 None。
    """
    # API 會預設回傳開啟的 PR，並按 created_at 降序排列，所以第一個就是最新的
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Accept": "application/vnd.github.v3+json", # 我們需要 JSON 回應
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    # 透過參數明確指定我們要的資料，更為穩健
    params = {
        "state": "open",      # 只看開啟的 PR
        "sort": "created",    # 根據創建時間排序
        "direction": "desc",  # 降序，最新的在最前面
        "per_page": 1,        # 我們只需要一個
        "page": 1
    }

    print(f"正在從 GitHub 獲取 {owner}/{repo} 最新的 PR 編號...")
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        pull_requests = response.json()

        if not pull_requests:
            print("🟡 在這個倉庫中找不到任何開啟的 Pull Request。")
            return None

        latest_pr_number = pull_requests[0]['number']
        print(f"✅ 成功找到最新的 PR 編號: #{latest_pr_number}")
        return latest_pr_number
    except requests.exceptions.RequestException as e:
        print(f"❌ 錯誤：無法從 GitHub 獲取 PR 列表。")
        if e.response is not None:
            print(f"   狀態碼: {e.response.status_code}")
            print(f"   回應: {e.response.text}")
        else:
            print(f"   錯誤訊息: {e}")
        return None

def get_pr_diff(owner: str, repo: str, pr_number: int, token: str) -> str | None:
    """
    從 GitHub 獲取指定 Pull Request 的 diff 內容。

    Args:
        owner: 倉庫擁有者。
        repo: 倉庫名稱。
        pr_number: Pull Request 編號。
        token: GitHub Personal Access Token。

    Returns:
        PR 的 diff 內容字串，如果發生錯誤則返回 None。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        # 我們要求 GitHub API 返回 diff 格式的內容
        "Accept": "application/vnd.github.v3.diff",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    print(f"正在從 GitHub 獲取 PR #{pr_number} 的 diff 內容...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # 如果 HTTP 狀態碼是 4xx 或 5xx，會拋出例外
        print("✅ 成功獲取 diff！")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"❌ 錯誤：無法從 GitHub 獲取 PR 內容。")
        if e.response is not None:
            print(f"   狀態碼: {e.response.status_code}")
            print(f"   回應: {e.response.text}")
        else:
            print(f"   錯誤訊息: {e}")
        return None
    
def post_review_to_github(owner: str, repo: str, pr_number: int, token: str, comment: str) -> None:
    """
    將 Code Review 結果作為留言發佈到指定的 GitHub Pull Request。

    Args:
        owner: 倉庫擁有者。
        repo: 倉庫名稱。
        pr_number: Pull Request 編號。
        token: GitHub Personal Access Token (需要 'pull-requests:write' 或 'issues:write' 權限)。
        comment: 要發佈的留言內容。
    """
    # PR 在 API 中也被視為一個 issue，所以我們使用 issue comment 的 API
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {"body": comment}

    print(f"正在將 Code Review 結果發佈到 PR #{pr_number}...")
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        print(f"✅ 成功將 Review 留言發佈到 PR #{pr_number}！")
        print(f"   留言網址: {response.json().get('html_url')}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 錯誤：無法將留言發佈到 GitHub PR。")
        if e.response is not None:
            print(f"   狀態碼: {e.response.status_code}")
            print(f"   回應: {e.response.text}")
            if e.response.status_code == 403:
                print("   提示：請檢查您的 GITHUB_TOKEN 是否具有 'pull-requests:write' 或 'issues:write' 權限。")
        else:
            print(f"   錯誤訊息: {e}")   

def get_gemini_review(diff: str, api_key: str) -> str | None:
    """
    使用 Gemini 2.5 Pro 來對程式碼的 diff 進行審查。
    """
    if not diff:
        print("❌ 錯誤：diff 內容為空，無法進行 Code Review。")
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        # 這是一個針對 Android 開發精心設計的 Prompt
        prompt = """
        您是一位資深的 Android 開發架構師與頂尖的程式碼審查專家，精通 Kotlin、Java 與 Android Jetpack。
        請根據以下的 pull request diff 內容，針對 Android App 開發提供一份專業、嚴謹且有建設性的程式碼審查報告，並使用【繁體中文】和【Markdown格式】進行回覆。

        您的審查應包含以下 Android 開發的重點：
        1.  **架構與設計模式**：評估是否遵循 MVVM, MVI 等現代 Android 架構。檢查 ViewModel、Repository、UseCase 的職責劃分是否清晰。
        2.  **生命週期管理 (Lifecycle)**：檢查是否有正確處理 Activity/Fragment 的生命週期，避免記憶體洩漏 (Memory Leaks)，例如：不當持有 Context、未取消的 Coroutines 或 RxJava subscriptions。
        3.  **UI/UX 實作**：
            *   **Jetpack Compose**: 檢查 Composable 函數是否高效、可重用且無副作用 (side-effects)。State 管理是否恰當。
            *   **XML Layouts**: 佈局層級是否過深？是否有效使用 `ConstraintLayout`？
        4.  **非同步處理**：評估 Coroutines 或 RxJava 的使用是否恰當，是否在正確的 Dispatcher 上執行任務，以及是否有妥善的錯誤處理。
        5.  **效能與資源**：
            *   指出可能有效能瓶頸或資源浪費的地方 (例如：主線程上的 I/O 操作、不必要的物件創建)。
            *   檢查圖片載入、快取策略是否有效率。
        6.  **Gradle 與相依性**：檢查是否有不推薦使用 (deprecated) 或有安全漏洞的函式庫。相依性管理是否合理。
        7.  **安全性**：檢查是否存在潛在的安全漏洞，例如：不安全的資料儲存、API Key 洩漏、不當的 Intent 處理等。
        8.  **Kotlin/Java 最佳實踐**：評估程式碼是否符合 Kotlin/Java 的慣例與風格指南。

        # 請以清晰、條列式的方式提供您的審查意見。
        # 在報告的最後，請明確總結您是否同意合併此 PR。
        # *   如果同意，請說明原因，並將所有建議的修改以 TODO 列表的形式呈現。
        # *   如果不同意，請說明具體原因，以及需要修改的地方。
        # 請在可能的情況下提供修改後的程式碼範例以供參考。
        
        **報告格式要求**：
        1.  在報告的開頭，請給出一個 **總體評論** (Overall Comments) 的總結。
        2.  接著，以 **條列式** 的方式，針對具體程式碼提出您的 **發現與建議** (Findings & Suggestions)。
        3.  對於每個建議，如果可能，請提供精簡的 **程式碼修改範例**。
        4.  報告應專注於技術層面的分析，保持客觀中立。


        --- 以下是 Pull Request 的 diff 內容 ---
        ```diff
        {diff}
        ```
        --- diff 內容結束 ---
        
        請開始您的 Android Code Review：
        """ 
        
        print("正在將 diff 傳送給 Gemini 2.5 Pro 進行 Code Review...")
        response = model.generate_content(prompt)
        print("✅ 成功收到 Gemini 的回覆！")
        return response.text
    except Exception as e:
        print(f"❌ 錯誤：呼叫 Gemini API 時發生問題: {e}")
        return None

def main():
    """主程式進入點"""
    load_dotenv() # 從 .env 檔案載入環境變數

    # 從環境變數讀取設定
    github_token = os.getenv("GITHUB_TOKEN")
    repo_owner = os.getenv("REPO_OWNER")
    repo_name = os.getenv("REPO_NAME")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    # 0. 檢查必要的環境變數
    if not all([github_token, repo_owner, repo_name, gemini_api_key]):
        print("❌ 錯誤：請確保 .env 檔案中已設定 GITHUB_TOKEN, REPO_OWNER, REPO_NAME, 和 GEMINI_API_KEY。")
        return

    # 1. 自動獲取最新的 PR 編號
    # pr_number = int(os.getenv("PR_NUMBER")) # 改為自動獲取
    pr_number = get_latest_pr_number(repo_owner, repo_name, github_token)

    if not pr_number:
        print("無法繼續進行 Code Review，因為沒有獲取到 PR 編號。")
        return

    # 2. 從 GitHub 取得 PR diff
    pr_diff = get_pr_diff(repo_owner, repo_name, pr_number, github_token)

    # 3. 如果成功取得 diff，就交給 Gemini 進行 Review
    if pr_diff:
        review = get_gemini_review(pr_diff, gemini_api_key)
        if review:
            # 在終端機印出結果
            print("\n" + "="*25 + " Gemini Code Review 報告 " + "="*25)
            print(f"Repository: {repo_owner}/{repo_name}")
            print(f"Pull Request: #{pr_number}\n")
            print(review)
            print("="*73 + "\n")

    # 4. 將 Review 結果發佈到 GitHub PR
            # 為了讓留言更美觀，加上一個標題和分隔線
            github_comment = f"### 🤖 Gemini AI Code Review\n\n---\n\n{review}"
            post_review_to_github(
                repo_owner, repo_name, pr_number, github_token, github_comment
            )        
if __name__ == "__main__":
    main()