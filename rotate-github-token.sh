#!/bin/bash
# GitHub Token 轮换助手
# 用法：
#   1. 在 https://github.com/settings/tokens 撤销旧 token (ghp_ikf2...ZrZcY)
#   2. 生成新 token（scope 选 repo + workflow）
#   3. 跑这个脚本，粘贴新 token
#   4. 验证 git push/pull 走新 token

set -e
# 旧 token 占位符（从 ~/.gitconfig 历史或 git remote -v 里复制）
OLD_TOKEN="<PASTE_OLD_TOKEN_HERE>"  # ← 从 git remote URL 里复制，不要 commit 真 token

# 待修复的仓库
REPOS=(
    "/Users/gongruolan/Documents/GitHub/agent-chat"
    "/Users/gongruolan/Documents/GitHub/catbot"
)

echo "=================================================="
echo "  GitHub Token 轮换助手"
echo "=================================================="
echo ""
echo "泄露的旧 token（前 8 位）: ${OLD_TOKEN:0:8}..."
echo ""
echo "📋 前置步骤（在 GitHub 网站操作）："
echo "  1. 打开 https://github.com/settings/tokens"
echo "  2. 找到 ghp_ikf2...ZrZcY 这个 token，点 'Delete' 撤销"
echo "  3. 点 'Generate new token' → 选 'Fine-grained personal access token' 或 'Classic'"
echo "  4. 设置："
echo "     - Note: 'agent-chat + catbot + agent-chat-multi'"
echo "     - Expiration: 90 days（或更长）"
echo "     - Scopes: repo (full), workflow (if needed)"
echo "  5. 点 'Generate token'，复制新 token（ghp_开头）"
echo ""

# 让用户选择：直接粘贴 token 或退出
echo "请粘贴新 token（输入 'q' 退出）："
read -r NEW_TOKEN

if [[ -z "$NEW_TOKEN" || "$NEW_TOKEN" == "q" || "$NEW_TOKEN" == "Q" ]]; then
    echo "退出"
    exit 0
fi

if [[ ! "$NEW_TOKEN" =~ ^ghp_[a-zA-Z0-9]{30,}$ ]]; then
    echo "❌ token 格式不对（应该是 ghp_ 开头 + 至少 30 个字符）"
    exit 1
fi

# 1. 替换所有仓库的 .git/config
echo ""
echo "🔧 替换 .git/config 里的 token..."

for repo in "${REPOS[@]}"; do
    if [ ! -d "$repo" ]; then
        echo "  ⚠️  仓库不存在: $repo"
        continue
    fi
    
    cd "$repo"
    
    # 找到所有 remote URL 里带旧 token 的，替换成新 token
    for remote in $(git remote); do
        URL=$(git config --get "remote.$remote.url")
        echo "  → $repo: remote '$remote' URL: $URL"
        
        if [[ "$URL" == *"$OLD_TOKEN"* ]]; then
            NEW_URL="${URL/$OLD_TOKEN/$NEW_TOKEN}"
            git remote set-url "$remote" "$NEW_URL"
            echo "    ✅ 已替换"
        else
            echo "    ⏭️  URL 里没有旧 token，跳过"
        fi
    done
done

# 2. 验证
echo ""
echo "🔍 验证新 token 是否能正常工作..."

for repo in "${REPOS[@]}"; do
    if [ ! -d "$repo" ]; then
        continue
    fi
    
    cd "$repo"
    echo ""
    echo "--- $repo ---"
    
    # 试 fetch（读权限测试）
    if git fetch --dry-run 2>&1 | tail -3; then
        echo "  ✅ fetch OK"
    else
        echo "  ❌ fetch FAIL（可能 token 没权限或格式错）"
    fi
done

echo ""
echo "=================================================="
echo "  ✅ 完成"
echo "=================================================="
echo ""
echo "📋 后续建议："
echo "  1. 测试 push: cd /path/to/repo && git push  # 应该成功"
echo "  2. 在 GitHub 网站确认旧 token 已撤销（不能用了）"
echo "  3. 把这个脚本加入 git 历史（不要），或保留作未来轮换用"
echo "  4. **绝对不要**把新 token 提交到 git 或聊天记录里"
echo ""
echo "💡 备份建议："
echo "  - macOS Keychain:  security add-generic-password -s 'github' -a 'gongruolan' -w 'NEW_TOKEN'"
echo "  - 1Password / Bitwarden 等密码管理器"
echo "  - 不要再 hardcode 到 .git/config（应该用 git credential helper）"
echo ""
