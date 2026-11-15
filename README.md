# GMI – URL共有版

## 公開方法（GitHub Pages）
1. GitHubで新しい **Public** リポジトリを作成します（例: `gmi`）。
2. このZIPを展開し、**中身をすべて**リポジトリのルートへアップロードします。`.github/workflows/daily.yml` も含めてください。GitHubのブラウザーからアップロードすると隠しフォルダの扱いに注意してください。
3. Settings → Pages → Build and deployment → Deploy from a branch → `main` / `(root)` → Save。
4. Actions → `Update market headlines` → Run workflow を実行します。
5. 公開URLは `https://<GitHubユーザー名>.github.io/<リポジトリ名>/` です。反映まで数分かかる場合があります。
6. 公開URLを友人に共有します。iPhoneではSafariの共有メニューから「ホーム画面に追加」できます。

## 仕様と注意
- 毎日日本時間6:15頃にGitHub Actionsが公開検索RSSから新着見出しを取得します。定時実行は保証されません。
- 収集対象は15機関。Google News RSSで公式ドメインを検索しますが、**公式記事であることを検証した結果ではありません**。リンク先と原文を確認してください。
- 収集された見出しはAI要約ではありません。評価変更検出・AI分析・通知は未実装です。
- GitHub Pagesでは公開リポジトリにデータを置きます。アクセス制限はありません。
- GitHub Actionsがリポジトリへpushできない場合はSettings → Actions → General → Workflow permissionsをRead and write permissionsにしてください（組織ポリシーによっては不可）。
- GitHub Actionsが停止・無効化される場合があります。Actions履歴を確認してください。
- 一部リンクはGoogle NewsのリダイレクトURLです。
- ブラウザーの「保存済み」はその端末だけに保存されます。
