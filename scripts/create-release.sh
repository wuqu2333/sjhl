#!/bin/bash
TOKEN=$1
APK=$2

# Create release
RESP=$(curl -s -X POST https://api.github.com/repos/wuqu2333/sjhl/releases \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tag_name":"v0.1.0","name":"SJHL Worker v0.1.0","body":"Android Worker APP - 连接主控服务器执行文件下载上传任务\n\n- 输入主控地址获取任务\n- 前台服务后台运行\n- 分片上传，断点续传","draft":false,"prerelease":false}')

echo "Release: $RESP"

UPLOAD_URL=$(echo "$RESP" | sed 's/.*"upload_url" *: *"\(https:\/\/[^{]*\){.*/\1/')
echo "Upload URL: $UPLOAD_URL"

curl -s -X POST "${UPLOAD_URL}?name=sjhl-worker-v0.1.0.apk" \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/vnd.android.package-archive" \
  --data-binary "@$APK"

echo ""
echo "DONE"
echo "Download: https://github.com/wuqu2333/sjhl/releases/tag/v0.1.0"
