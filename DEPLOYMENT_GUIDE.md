# 阳坊涮肉套餐毛利测算工具 - 线上部署指南

## 步骤1：创建GitHub仓库

1. **访问GitHub**：打开浏览器，访问 https://github.com
2. **登录账户**：使用您的GitHub账号登录
3. **创建新仓库**：
   - 点击右上角的 "+" 图标
   - 选择 "New repository"
   - 填写仓库名称：`yangfang-profit-tool`
   - 选择仓库类型：Public（公开）或 Private（私有）
   - 点击 "Create repository"

## 步骤2：推送本地代码到GitHub

1. **复制仓库URL**：在GitHub仓库页面，点击绿色的 "Code" 按钮，复制HTTPS URL（格式：https://github.com/your-username/yangfang-profit-tool.git）

2. **打开终端**：在您的电脑上打开终端，进入项目目录

3. **添加远程仓库**：
   ```bash
   git remote add origin https://github.com/your-username/yangfang-profit-tool.git
   ```

4. **推送代码**：
   ```bash
   git push -u origin main
   ```

## 步骤3：在Render上部署应用

1. **访问Render**：打开浏览器，访问 https://render.com
2. **登录账户**：使用您的GitHub账号登录
3. **创建新服务**：
   - 点击 "New" → "Web Service"
   - 选择您的GitHub仓库：`yangfang-profit-tool`
   - 点击 "Connect"

4. **配置部署**：
   - **Name**：yangfang-profit-tool
   - **Region**：选择一个离您最近的区域
   - **Branch**：main
   - **Root Directory**：backend
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`gunicorn --bind 0.0.0.0:$PORT app:app`
   - **Plan**：Free

5. **点击 "Create Web Service"**：开始部署过程

## 步骤4：配置环境变量

1. **等待部署完成**：部署过程可能需要1-2分钟
2. **配置环境变量**：
   - 在Render控制台，进入您的服务
   - 点击 "Environment" 标签
   - 添加环境变量（如果需要）

## 步骤5：访问应用

1. **获取应用URL**：部署完成后，Render会提供一个URL（格式：https://yangfang-profit-tool.onrender.com）
2. **访问应用**：在浏览器中打开该URL
3. **登录认证**：使用以下凭据登录：
   - 用户名：admin
   - 密码：password

## 步骤6：更新前端代码中的API地址

1. **打开前端文件**：`profit-tool-25.html`
2. **查找API地址**：搜索 `http://127.0.0.1:5002/api/libraries`
3. **替换为Render URL**：将其替换为您的Render应用URL，例如：`https://yangfang-profit-tool.onrender.com/api/libraries`
4. **推送更新**：
   ```bash
   git add profit-tool-25.html
   git commit -m "Update API URL"
   git push
   ```

## 注意事项

1. **免费计划限制**：Render的免费计划会在15分钟无活动后休眠，首次请求需要约10-20秒冷启动
2. **数据持久化**：Render的免费计划不提供持久化存储，数据库会在每次部署时重置
3. **安全考虑**：在生产环境中，建议修改默认的用户名和密码
4. **备份数据**：定期使用应用的 "备份数据" 功能导出数据

## 故障排除

- **部署失败**：检查构建日志，确保所有依赖都已正确安装
- **API访问失败**：确保前端代码中的API地址正确，且后端服务正在运行
- **认证失败**：检查用户名和密码是否正确

如果遇到任何问题，请参考Render的文档或联系Render支持。
