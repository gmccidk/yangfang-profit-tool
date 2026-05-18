# 阳坊涮肉套餐毛利测算工具 - PythonAnywhere部署指南

## 步骤1：注册PythonAnywhere账号

1. **访问PythonAnywhere**：打开浏览器，访问 https://www.pythonanywhere.com
2. **创建账号**：
   - 点击 "Start running Python online"
   - 选择 "Create a Beginner account"（免费）
   - 填写注册信息，不需要信用卡

## 步骤2：上传项目代码

1. **登录PythonAnywhere**：使用您的账号登录
2. **进入Files标签**：在Dashboard中点击 "Files"
3. **上传文件**：
   - 点击 "Upload a file" 按钮
   - 上传以下文件：
     - `profit-tool-25.html`
     - `yangfang-logo.png`
     - `backend/app.py`
     - `backend/requirements.txt`
     - `backend/schema.sql`

4. **创建目录结构**：
   - 点击 "New directory" 按钮
   - 创建 `backend` 目录
   - 将 `app.py`、`requirements.txt` 和 `schema.sql` 移动到 `backend` 目录

## 步骤3：创建虚拟环境并安装依赖

1. **进入Consoles标签**：在Dashboard中点击 "Consoles"
2. **启动Bash控制台**：点击 "Bash"
3. **创建虚拟环境**：
   ```bash
   mkvirtualenv --python=python3.9 my-virtualenv
   ```
4. **激活虚拟环境**：
   ```bash
   workon my-virtualenv
   ```
5. **安装依赖**：
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

## 步骤4：配置Web应用

1. **进入Web标签**：在Dashboard中点击 "Web"
2. **创建新Web应用**：
   - 点击 "Add a new web app"
   - 选择 "Manual configuration"
   - 选择 Python 3.9（与虚拟环境版本一致）
   - 点击 "Next"

3. **配置虚拟环境**：
   - 在 "Virtualenv" 部分，输入 `my-virtualenv`
   - 点击 "Enter"，系统会自动填充完整路径

4. **配置WSGI文件**：
   - 点击 "WSGI configuration file" 链接
   - 编辑文件内容，替换为：
     ```python
     import sys
     path = '/home/your-username/backend'
     if path not in sys.path:
         sys.path.append(path)

     from app import app as application
     ```
   - 注意：将 `your-username` 替换为您的PythonAnywhere用户名

5. **配置静态文件**：
   - 在 "Static files" 部分，添加：
     - URL: `/static`
     - Directory: `/home/your-username`
   - 注意：将 `your-username` 替换为您的PythonAnywhere用户名

## 步骤5：部署应用

1. **重新加载应用**：点击 "Reload your-username.pythonanywhere.com"
2. **访问应用**：
   - 应用地址：https://your-username.pythonanywhere.com
   - 注意：将 `your-username` 替换为您的PythonAnywhere用户名

3. **登录认证**：使用以下凭据登录：
   - 用户名：admin
   - 密码：password

## 步骤6：更新前端代码中的API地址

1. **编辑前端文件**：在PythonAnywhere的Files标签中，编辑 `profit-tool-25.html`
2. **查找API地址**：搜索 `http://127.0.0.1:5002/api/libraries`
3. **替换为PythonAnywhere URL**：将其替换为您的PythonAnywhere应用URL，例如：`https://your-username.pythonanywhere.com/api/libraries`
4. **重新加载应用**：在Web标签中点击 "Reload your-username.pythonanywhere.com"

## 注意事项

1. **免费计划限制**：PythonAnywhere的免费计划有以下限制：
   - 每月500MB磁盘空间
   - 有限的CPU时间
   - 不支持持续运行的进程

2. **数据持久化**：PythonAnywhere的免费计划提供持久化存储，数据库会保存

3. **安全考虑**：在生产环境中，建议修改默认的用户名和密码

4. **备份数据**：定期使用应用的 "备份数据" 功能导出数据

## 故障排除

- **部署失败**：检查WSGI文件配置是否正确，确保虚拟环境已激活
- **API访问失败**：确保前端代码中的API地址正确，且后端服务正在运行
- **认证失败**：检查用户名和密码是否正确

如果遇到任何问题，请参考PythonAnywhere的文档或联系PythonAnywhere支持。
