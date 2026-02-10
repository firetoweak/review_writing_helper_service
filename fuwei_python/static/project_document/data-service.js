// static/project_document/data-service.js

// 项目文档数据服务
const ProjectDocumentService = {
    /**
     * 获取写作工作区数据
     * @param {number} documentId - 文档ID
     * @returns {Promise<Object>} 工作区数据
     */
    async getWorkspaceData(documentId) {
        try {
            const response = await fetch(`/project_document/${documentId}/writing-workspace`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200 && result.data) {
                return result.data;
            } else {
                throw new Error(result.message || '获取数据失败');
            }
        } catch (error) {
            console.error('获取工作区数据失败:', error);
            throw error;
        }
    },

    /**
     * 获取 小章节或章节 内容，包括评审数据
     * @param {number} documentId - 文档ID
     * @param {string} nodeId - 节点ID
     * @returns {Promise<Object>} 章节数据
     */
    async getSectionContent(documentId, nodeId) {
        try {
            const response = await fetch(`/project_document/${documentId}/section/${nodeId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200 && result.data) {
                return result.data;
            } else {
                throw new Error(result.message || '获取章节内容失败');
            }
        } catch (error) {
            console.error('获取章节内容失败:', error);
            throw error;
        }
    },

     /**
     * 获取 章节/小节 内容，不包括评审数据
     * @param {number} documentId - 文档ID
     * @param {string} nodeId - 节点ID
     * @returns {Promise<Object>} 章节数据
     */
    async getSectionContentOnly(documentId, nodeId) {
        try {
            const response = await fetch(`/project_document/${documentId}/section-content/${nodeId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200 && result.data) {
                return result.data;
            } else {
                throw new Error(result.message || '获取章节/小节内容失败');
            }
        } catch (error) {
            console.error('获取章节/小节内容失败:', error);
            throw error;
        }
    },

    /**
     * 保存章节内容
     * @param {number} documentId - 文档ID
     * @param {string} nodeId - 节点ID
     * @param {Object} data - 保存的数据
     * @returns {Promise<Object>} 保存结果
     */
    async saveSectionContent(documentId, nodeId, data) {
        try {
            const response = await fetch(`/project_document/${documentId}/section/${nodeId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '保存失败');
            }
        } catch (error) {
            console.error('保存章节内容失败:', error);
            throw error;
        }
    },

    /**
     * 新增对话消息
     * @param {Object} data - 对话消息数据
     * @returns {Promise<Object>} 添加结果
     */
    async addConversationMessage(data) {
        try {
            const response = await fetch('/project_document/conversation-messages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '添加对话消息失败');
            }
        } catch (error) {
            console.error('添加对话消息失败:', error);
            throw error;
        }
    },

    /**
     * 删除对话消息
     * @param {number} messageId - 对话消息ID
     * @returns {Promise<Object>} 删除结果
     */
    async deleteConversationMessage(messageId) {
        try {
            const response = await fetch(`/project_document/conversation-messages/${messageId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '删除对话消息失败');
            }
        } catch (error) {
            console.error('删除对话消息失败:', error);
            throw error;
        }
    },

    /**
     * 加入改进笔记
     * @param {Object} data - 改进笔记数据
     * @returns {Promise<Object>} 添加结果
     */
    async addImprovementDraft(data) {
        try {
            const response = await fetch('/project_document/improvement-drafts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '添加改进笔记失败');
            }
        } catch (error) {
            console.error('添加改进笔记失败:', error);
            throw error;
        }
    },

    /**
     * 删除改进笔记
     * @param {number} draftId - 草稿ID
     * @returns {Promise<Object>} 删除结果
     */
    async deleteImprovementDraft(draftId) {
        try {
            const response = await fetch(`/project_document/improvement-drafts/${draftId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '删除改进笔记失败');
            }
        } catch (error) {
            console.error('删除改进笔记失败:', error);
            throw error;
        }
    },

    /**
     * 获取改进笔记列表
     * @param {number} documentId - 文档ID
     * @param {string} nodeId - 节点ID
     * @param {string} sourceType - 来源类型 (可选)
     * @param {boolean} isMerged - 是否已合入 (可选)
     * @param {boolean} isDeleted - 是否已删除 (可选)
     * @returns {Promise<Object>} 改进笔记列表
     */
    async getImprovementDrafts(documentId, nodeId, sourceType = null, isMerged = null, isDeleted = false) {
        try {
            let url = `/project_document/improvement-drafts?document_id=${documentId}&node_id=${nodeId}&is_deleted=${isDeleted}`;

            if (sourceType) {
                url += `&source_type=${sourceType}`;
            }

            if (isMerged !== null) {
                url += `&is_merged=${isMerged}`;
            }

            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '获取改进笔记列表失败');
            }
        } catch (error) {
            console.error('获取改进笔记列表失败:', error);
            throw error;
        }
    },

     /**
     * 获取对话消息列表
     * @param {number} documentId - 文档ID
     * @param {string} nodeId - 节点ID
     * @param {number} draftId - 改进草稿ID
     * @returns {Promise<Object>} 对话消息数据
     */
    async getConversationMessages(documentId, nodeId, draftId) {
        try {
            let url = `/project_document/conversation-messages?document_id=${documentId}&draft_id=${draftId}`;

            if (nodeId) {
                url += `&node_id=${nodeId}`;
            }

            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '获取对话消息失败');
            }
        } catch (error) {
            console.error('获取对话消息失败:', error);
            throw error;
        }
    },

    /**
     * 开始AI帮助会话（处理混合格式响应）
     * @param {Object} params - 请求参数
     * @param {number} params.document_id - 文档ID
     * @param {string} params.node_id - 节点ID
     * @param {string} params.help_text - 帮助文本
     * @returns {Promise<Object>} 包含流式处理器和初始会话信息
     */
    async startHelpSession(params) {
        try {
            const response = await fetch('/project_document/help/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    document_id: params.document_id,
                    node_id: params.node_id,
                    help_text: params.help_text,
                    session_id: params.session_id
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // 创建流式响应处理器（支持混合格式）
            const streamHandler = {
                reader: response.body.getReader(),
                decoder: new TextDecoder('utf-8'),
                buffer: '',
                sessionId: null,
                messageId: null,

                /**
                 * 处理混合格式的流式响应
                 * @param {Function} onChunk - 处理数据块的回调函数
                 * @param {Function} onComplete - 处理完成回调函数
                 * @param {Function} onError - 错误处理回调函数
                 */
                async process(onChunk, onComplete, onError) {
                    try {
                        let fullMessage = '';

                        while (true) {
                            const { done, value } = await this.reader.read();

                            if (done) {
                                // 流处理完成
                                if (onComplete) {
                                    onComplete({
                                        session_id: this.sessionId,
                                        message_id: this.messageId,
                                        full_message: fullMessage
                                    });
                                }
                                break;
                            }

                            // 解码数据并添加到缓冲区
                            this.buffer += this.decoder.decode(value, { stream: true });

                            // 处理缓冲区中的数据
                            await this.processBuffer(onChunk, (delta) => {
                                fullMessage += delta;
                            });

                            // 检查是否有完整的JSON对象在缓冲区开头
                            await this.tryParseInitialJson();
                        }
                    } catch (error) {
                        console.error('处理流式响应失败:', error);
                        if (onError) {
                            onError(error);
                        }
                    }
                },

                /**
                 * 处理缓冲区中的数据（支持混合格式）
                 */
                async processBuffer(onChunk, onDelta) {
                    // 尝试从缓冲区开头提取并解析JSON对象
                    const jsonMatch = this.buffer.match(/^\{[^]*?\}(?=\S|$)/);

                    if (jsonMatch) {
                        try {
                            const jsonStr = jsonMatch[0];
                            const data = JSON.parse(jsonStr);

                            // 处理会话信息
                            if (data.session_id && data.message_id) {
                                this.sessionId = data.session_id;
                                this.messageId = data.message_id;

                                // 移除已处理的JSON部分
                                this.buffer = this.buffer.slice(jsonStr.length);

                                // 如果JSON后面还有内容，直接作为文本处理
                                if (this.buffer.trim()) {
                                    const textDelta = this.buffer;
                                    if (onChunk) onChunk(textDelta);
                                    if (onDelta) onDelta(textDelta);
                                    this.buffer = '';
                                }
                                return;
                            }

                            // 如果有delta字段
                            if (data.delta) {
                                if (onChunk) onChunk(data.delta);
                                if (onDelta) onDelta(data.delta);
                                this.buffer = this.buffer.slice(jsonStr.length);
                                return;
                            }

                            // 如果解析成功但没有需要处理的字段，直接移除JSON
                            this.buffer = this.buffer.slice(jsonStr.length);

                        } catch (parseError) {
                            // JSON解析失败，将整个缓冲区作为文本处理
                            console.warn('JSON解析失败，作为文本处理:', parseError);
                        }
                    }

                    // 如果没有JSON或解析失败，将整个缓冲区作为文本处理
                    if (this.buffer.trim()) {
                        if (onChunk) onChunk(this.buffer);
                        if (onDelta) onDelta(this.buffer);
                        this.buffer = '';
                    }
                },

                /**
                 * 尝试从缓冲区开头解析初始JSON
                 */
                async tryParseInitialJson() {
                    // 尝试匹配可能存在的JSON对象
                    const jsonMatch = this.buffer.match(/^\{[^]*?\}(?=\S|$)/);
                    if (jsonMatch) {
                        try {
                            const data = JSON.parse(jsonMatch[0]);
                            if (data.session_id && data.message_id) {
                                this.sessionId = data.session_id;
                                this.messageId = data.message_id;
                            }
                        } catch (error) {
                            // 忽略解析错误
                        }
                    }
                },

                /**
                 * 取消/关闭流
                 */
                cancel() {
                    if (this.reader) {
                        this.reader.cancel();
                    }
                }
            };

            return {
                code: 200,
                data: {
                    stream: streamHandler,
                    session_id: null, // 将在流处理过程中获取
                    message_id: null  // 将在流处理过程中获取
                },
                message: 'AI帮助请求已启动，请使用流处理器接收数据'
            };

        } catch (error) {
            console.error('AI帮助请求失败:', error);
            throw error;
        }
    },

    /**
     * 发送AI帮助回复（流式响应）
     * @param {Object} params - 请求参数
     * @param {number} params.document_id - 文档ID
     * @param {string} params.node_id - 节点ID
     * @param {string} params.session_id - 会话ID
     * @param {string} params.message - 用户消息
     * @param {string} params.message_id - 消息ID
     * @param {Object} params.attachment - 附件信息
     * @returns {Promise<Object>} 包含流式处理器
     */
    async sendHelpResponse(params) {
        try {
            const response = await fetch('/project_document/help/response', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    document_id: params.document_id,
                    node_id: params.node_id,
                    session_id: params.session_id,
                    message: params.message,
                    message_id: params.message_id,
                    attachment: params.attachment || {}
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // 创建流式响应处理器（支持混合格式）
            const streamHandler = {
                reader: response.body.getReader(),
                decoder: new TextDecoder('utf-8'),
                buffer: '',

                /**
                 * 处理流式响应
                 * @param {Function} onChunk - 处理数据块的回调函数
                 * @param {Function} onComplete - 处理完成回调函数
                 * @param {Function} onError - 错误处理回调函数
                 */
                async process(onChunk, onComplete, onError) {
                    try {
                        let fullMessage = '';
                        let newSessionId = params.session_id;
                        let newMessageId = null;

                        while (true) {
                            const { done, value } = await this.reader.read();

                            if (done) {
                                // 流处理完成
                                if (onComplete) {
                                    onComplete({
                                        session_id: newSessionId,
                                        message_id: newMessageId,
                                        full_message: fullMessage,
                                        assistant_message: fullMessage
                                    });
                                }
                                break;
                            }

                            // 解码数据并添加到缓冲区
                            this.buffer += this.decoder.decode(value, { stream: true });

                            // 尝试处理缓冲区中的数据
                            const jsonMatch = this.buffer.match(/^\{[^]*?\}(?=\S|$)/);

                            if (jsonMatch) {
                                try {
                                    const data = JSON.parse(jsonMatch[0]);

                                    // 处理会话信息
                                    if (data.session_id && data.message_id) {
                                        newSessionId = data.session_id;
                                        newMessageId = data.message_id;
                                        this.buffer = this.buffer.slice(jsonMatch[0].length);

                                        // 如果JSON后面还有内容，作为文本处理
                                        if (this.buffer.trim()) {
                                            const textDelta = this.buffer;
                                            fullMessage += textDelta;
                                            if (onChunk) onChunk(textDelta);
                                            this.buffer = '';
                                        }
                                        continue;
                                    }

                                    // 处理delta字段
                                    if (data.delta) {
                                        fullMessage += data.delta;
                                        if (onChunk) onChunk(data.delta);
                                        this.buffer = this.buffer.slice(jsonMatch[0].length);
                                        continue;
                                    }

                                    // 移除已处理的JSON
                                    this.buffer = this.buffer.slice(jsonMatch[0].length);

                                } catch (parseError) {
                                    // JSON解析失败，将整个缓冲区作为文本处理
                                    console.warn('JSON解析失败，作为文本处理:', parseError);
                                }
                            }

                            // 处理剩余的文本内容
                            if (this.buffer.trim()) {
                                fullMessage += this.buffer;
                                if (onChunk) onChunk(this.buffer);
                                this.buffer = '';
                            }
                        }
                    } catch (error) {
                        console.error('处理流式响应失败:', error);
                        if (onError) {
                            onError(error);
                        }
                    }
                },

                /**
                 * 取消/关闭流
                 */
                cancel() {
                    if (this.reader) {
                        this.reader.cancel();
                    }
                }
            };

            return {
                code: 200,
                data: {
                    stream: streamHandler,
                    session_id: params.session_id
                },
                message: '回复已发送，请使用流处理器接收数据'
            };

        } catch (error) {
            console.error('获取AI回复失败:', error);
            throw error;
        }
    },

    /**
     * 章节评审
     * @param {Object} params - 请求参数
     * @param {number} params.document_id - 文档ID
     * @param {string} params.node_id - 节点ID
     * @param {string} params.session_id - 会话ID
     * @returns {Promise<Object>} 评审结果
     */
    async reviewSection(params) {
        try {
            const response = await fetch('/project_document/review/section', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200 && result.data) {
                return result.data;
            } else {
                throw new Error(result.message || '章节评审失败');
            }
        } catch (error) {
            console.error('章节评审失败:', error);
            throw error;
        }
    },

    /**
     * 合并草稿
     * @param {Object} params - 请求参数
     * @param {number} params.document_id - 文档ID
     * @param {string} params.node_id - 节点ID
     * @param {Array} params.session_list - 会话列表
     * @returns {Promise<Object>} 合并结果
     */
    async mergeDrafts(params) {
        try {
            const response = await fetch('/project_document/merge', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200 && result.data) {
                return result.data;
            } else {
                throw new Error(result.message || '合入失败');
            }
        } catch (error) {
            console.error('合入失败:', error);
            throw error;
        }
    },

    /**
     * 上传文件
     * @param {File} file - 文件对象
     * @returns {Promise<Object>} 上传结果
     */
    async uploadFile(file) {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/project_document/upload', {
                method: 'POST',
                body: formData
            });

            return await response.json();
        } catch (error) {
            console.error('文件上传失败:', error);
            throw error;
        }
    },

    /**
     * 上传图片
     * @param {File} file - 图片文件对象
     * @returns {Promise<Object>} 上传结果
     */
    async uploadImg(file) {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/user/aiVal/upload_pic', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            // 根据后端接口返回格式处理
            if (result.code === 1) {
                return {
                    code: 200,
                    data: {
                        url: result.url
                    },
                    message: result.msg || '图片上传成功'
                };
            } else {
                throw new Error(result.msg || '图片上传失败');
            }
        } catch (error) {
            console.error('图片上传失败:', error);
            throw error;
        }
    },

    /**
     * 删除文件
     * @param {string} filePath - 文件路径
     * @param {string} fileUrl - 文件URL
     * @returns {Promise<Object>} 删除结果
     */
    async deleteFile(filePath, fileUrl) {
        try {
            const response = await fetch('/project_document/delete-file', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    file_path: filePath,
                    url: fileUrl
                })
            });

            return await response.json();
        } catch (error) {
            console.error('删除文件失败:', error);
            throw error;
        }
    },

    /**
     * 获取行业列表
     * @returns {Promise<Array>} 行业列表
     */
    async getIndustryList() {
        try {
            const response = await fetch('/project_document/industry/list', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '获取行业列表失败');
            }
        } catch (error) {
            console.error('获取行业列表失败:', error);
            throw error;
        }
    },

    /**
     * 获取大纲规则
     * @returns {Promise<Array>} 大纲规则列表
     */
    async getOutlineRules() {
        try {
            const response = await fetch('/project_document/rules/outline', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '获取大纲规则失败');
            }
        } catch (error) {
            console.error('获取大纲规则失败:', error);
            throw error;
        }
    },

    /**
     * 获取评审规则
     * @returns {Promise<Array>} 评审规则列表
     */
    async getReviewRules() {
        try {
            const response = await fetch('/project_document/rules/review', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '获取评审规则失败');
            }
        } catch (error) {
            console.error('获取评审规则失败:', error);
            throw error;
        }
    },

    /**
     * 获取任务状态
     * @param {string} taskUuid - 任务UUID
     * @returns {Promise<Object>} 任务状态
     */
    async getTaskStatus(taskUuid) {
        try {
            const response = await fetch(`/project_document/tasks/${taskUuid}/status`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '获取任务状态失败');
            }
        } catch (error) {
            console.error('获取任务状态失败:', error);
            throw error;
        }
    },

    /**
     * 选择/取消选择草稿
     * @param {number} draftId - 草稿ID
     * @param {boolean} isSelected - 是否选择
     * @returns {Promise<Object>} 操作结果
     */
    async selectDraft(draftId, isSelected = true) {
        try {
            const response = await fetch(`/project_document/drafts/${draftId}/select`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ is_selected: isSelected })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '选择草稿失败');
            }
        } catch (error) {
            console.error('选择草稿失败:', error);
            throw error;
        }
    },

    /**
     * 导出文档
     * @param {number} documentId - 文档ID
     * @param {string} format - 导出格式 (json|markdown|html)
     * @returns {Promise<Object>} 导出结果
     */
    async exportDocument(documentId, format = 'json') {
        try {
            const response = await fetch(`/project_document/${documentId}/export?format=${format}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '导出文档失败');
            }
        } catch (error) {
            console.error('导出文档失败:', error);
            throw error;
        }
    },

    /**
     * 获取预览数据
     * @param {number} documentId - 文档ID
     * @returns {Promise<Object>} 预览数据
     */
    async getPreviewData(documentId) {
        try {
            const response = await fetch(`/project_document/${documentId}/preview-data`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '获取预览数据失败');
            }
        } catch (error) {
            console.error('获取预览数据失败:', error);
            throw error;
        }
    },

    /**
     * 开始启发式写作（流式响应）
     * @param {Object} params - 请求参数
     * @param {number} params.document_id - 文档ID
     * @param {string} params.node_id - 节点ID
     * @param {string} params.session_id - 会话ID
     * @param {string} params.text - 初始文本
     * @returns {Promise<Object>} 包含流式处理器和初始会话信息
     */
    async startHeuristicWriting(params) {
        try {
            const response = await fetch('/project_document/heuristic-writing/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // 创建流式响应处理器（支持混合格式）
            const streamHandler = {
                reader: response.body.getReader(),
                decoder: new TextDecoder('utf-8'),
                buffer: '',
                sessionId: null,
                messageId: null,

                /**
                 * 处理混合格式的流式响应
                 * @param {Function} onChunk - 处理数据块的回调函数
                 * @param {Function} onComplete - 处理完成回调函数
                 * @param {Function} onError - 错误处理回调函数
                 */
                async process(onChunk, onComplete, onError) {
                    try {
                        let fullMessage = '';

                        while (true) {
                            const { done, value } = await this.reader.read();

                            if (done) {
                                // 流处理完成
                                if (onComplete) {
                                    onComplete({
                                        session_id: this.sessionId,
                                        message_id: this.messageId,
                                        full_message: fullMessage
                                    });
                                }
                                break;
                            }

                            // 解码数据并添加到缓冲区
                            this.buffer += this.decoder.decode(value, { stream: true });

                            // 处理缓冲区中的数据
                            await this.processBuffer(onChunk, (delta) => {
                                fullMessage += delta;
                            });

                            // 检查是否有完整的JSON对象在缓冲区开头
                            await this.tryParseInitialJson();
                        }
                    } catch (error) {
                        console.error('处理流式响应失败:', error);
                        if (onError) {
                            onError(error);
                        }
                    }
                },

                /**
                 * 处理缓冲区中的数据（支持混合格式）
                 */
                async processBuffer(onChunk, onDelta) {
                    // 尝试从缓冲区开头提取并解析JSON对象
                    const jsonMatch = this.buffer.match(/^\{[^]*?\}(?=\S|$)/);

                    if (jsonMatch) {
                        try {
                            const jsonStr = jsonMatch[0];
                            const data = JSON.parse(jsonStr);

                            // 处理会话信息
                            if (data.session_id && data.message_id) {
                                this.sessionId = data.session_id;
                                this.messageId = data.message_id;

                                // 移除已处理的JSON部分
                                this.buffer = this.buffer.slice(jsonStr.length);

                                // 如果JSON后面还有内容，直接作为文本处理
                                if (this.buffer.trim()) {
                                    const textDelta = this.buffer;
                                    if (onChunk) onChunk(textDelta);
                                    if (onDelta) onDelta(textDelta);
                                    this.buffer = '';
                                }
                                return;
                            }

                            // 如果有delta字段
                            if (data.delta) {
                                if (onChunk) onChunk(data.delta);
                                if (onDelta) onDelta(data.delta);
                                this.buffer = this.buffer.slice(jsonStr.length);
                                return;
                            }

                            // 如果解析成功但没有需要处理的字段，直接移除JSON
                            this.buffer = this.buffer.slice(jsonStr.length);

                        } catch (parseError) {
                            // JSON解析失败，将整个缓冲区作为文本处理
                            console.warn('JSON解析失败，作为文本处理:', parseError);
                        }
                    }

                    // 如果没有JSON或解析失败，将整个缓冲区作为文本处理
                    if (this.buffer.trim()) {
                        if (onChunk) onChunk(this.buffer);
                        if (onDelta) onDelta(this.buffer);
                        this.buffer = '';
                    }
                },

                /**
                 * 尝试从缓冲区开头解析初始JSON
                 */
                async tryParseInitialJson() {
                    // 尝试匹配可能存在的JSON对象
                    const jsonMatch = this.buffer.match(/^\{[^]*?\}(?=\S|$)/);
                    if (jsonMatch) {
                        try {
                            const data = JSON.parse(jsonMatch[0]);
                            if (data.session_id && data.message_id) {
                                this.sessionId = data.session_id;
                                this.messageId = data.message_id;
                            }
                        } catch (error) {
                            // 忽略解析错误
                        }
                    }
                },

                /**
                 * 取消/关闭流
                 */
                cancel() {
                    if (this.reader) {
                        this.reader.cancel();
                    }
                }
            };

            return {
                code: 200,
                data: {
                    stream: streamHandler,
                    session_id: null, // 将在流处理过程中获取
                    message_id: null  // 将在流处理过程中获取
                },
                message: '启发式写作已启动，请使用流处理器接收数据'
            };

        } catch (error) {
            console.error('启发式写作请求失败:', error);
            throw error;
        }
    },

    /**
     * 发送启发式写作回复（流式响应）
     * @param {Object} params - 请求参数
     * @param {number} params.document_id - 文档ID
     * @param {string} params.node_id - 节点ID
     * @param {string} params.session_id - 会话ID
     * @param {string} params.message - 用户消息
     * @param {string} params.message_id - 消息ID
     * @param {Object} params.attachment - 附件信息
     * @returns {Promise<Object>} 包含流式处理器
     */
    async sendHeuristicResponse(params) {
        try {
            const response = await fetch('/project_document/heuristic-writing/response', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    document_id: params.document_id,
                    node_id: params.node_id,
                    session_id: params.session_id,
                    messages: params.messages,
                    message_id: params.message_id,
                    attachment: params.attachment || {}
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // 创建流式响应处理器（支持混合格式）
            const streamHandler = {
                reader: response.body.getReader(),
                decoder: new TextDecoder('utf-8'),
                buffer: '',

                /**
                 * 处理流式响应
                 * @param {Function} onChunk - 处理数据块的回调函数
                 * @param {Function} onComplete - 处理完成回调函数
                 * @param {Function} onError - 错误处理回调函数
                 */
                async process(onChunk, onComplete, onError) {
                    try {
                        let fullMessage = '';
                        let newSessionId = params.session_id;
                        let newMessageId = null;
                        let finalStatus = 'ask'; // 使用不同的变量名避免混淆

                        while (true) {
                            const { done, value } = await this.reader.read();

                            if (done) {
                                // 流处理完成
                                if (onComplete) {
                                    onComplete({
                                        session_id: newSessionId,
                                        message_id: newMessageId,
                                        full_message: fullMessage,
                                        status: finalStatus  // 使用 finalStatus
                                    });
                                }
                                break;
                            }

                            // 解码数据并添加到缓冲区
                            this.buffer += this.decoder.decode(value, { stream: true });

                            // 尝试处理缓冲区中的数据
                            const jsonMatch = this.buffer.match(/^\{[^]*?\}(?=\S|$)/);

                            if (jsonMatch) {
                                try {
                                    const data = JSON.parse(jsonMatch[0]);

                                    // 处理会话信息
                                    if (data.session_id && data.message_id) {
                                        newSessionId = data.session_id;
                                        newMessageId = data.message_id;
                                        // 不要立即清空 buffer，可能后面还有文本
                                        this.buffer = this.buffer.slice(jsonMatch[0].length);
                                        // 继续处理，不要 return 或 continue
                                    }

                                    // 处理状态信息
                                    if (data.status) {
                                        finalStatus = data.status;  // 更新状态
                                        // 移除已处理的JSON
                                        if (!(data.session_id && data.message_id)) {
                                            this.buffer = this.buffer.slice(jsonMatch[0].length);
                                        }
                                        // 继续处理，不要 return 或 continue
                                    }

                                    // 处理 delta 字段
                                    if (data.delta) {
                                        fullMessage += data.delta;
                                        if (onChunk) onChunk(data.delta);
                                        this.buffer = this.buffer.slice(jsonMatch[0].length);
                                        continue;
                                    }

                                    // 如果没有处理任何特定字段，移除已处理的JSON
                                    if (!(data.session_id || data.message_id || data.status || data.delta)) {
                                        this.buffer = this.buffer.slice(jsonMatch[0].length);
                                    }

                                } catch (parseError) {
                                    // JSON解析失败，将整个缓冲区作为文本处理
                                    console.warn('JSON解析失败，作为文本处理:', parseError);
                                }
                            }

                            // 处理剩余的文本内容
                            if (this.buffer.trim()) {
                                // 确保文本内容被正确处理
                                const textContent = this.buffer;
                                fullMessage += textContent;
                                if (onChunk) onChunk(textContent);
                                this.buffer = '';
                            }
                        }
                    } catch (error) {
                        console.error('处理流式响应失败:', error);
                        if (onError) {
                            onError(error);
                        }
                    }
                },

                /**
                 * 取消/关闭流
                 */
                cancel() {
                    if (this.reader) {
                        this.reader.cancel();
                    }
                }
            };

            return {
                code: 200,
                data: {
                    stream: streamHandler,
                    session_id: params.session_id
                },
                message: '回复已发送，请使用流处理器接收数据'
            };

        } catch (error) {
            console.error('获取启发式回复失败:', error);
            throw error;
        }
    },

    /**
     * 全文评审
     * @param {number} documentId - 文档ID
     * @returns {Promise<Object>} 评审结果
     */
    async reviewFullDocument(documentId) {
        try {
            const response = await fetch('/project_document/review/full', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ document_id: documentId })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '全文评审失败');
            }
        } catch (error) {
            console.error('全文评审失败:', error);
            throw error;
        }
    },

    /**
     * 全文AI润色
     * @param {number} documentId - 文档ID
     * @returns {Promise<Object>} 润色结果
     */
    async polishFullDocument(documentId) {
        try {
            const response = await fetch('/project_document/polish/full', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ document_id: documentId })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '全文润色失败');
            }
        } catch (error) {
            console.error('全文润色失败:', error);
            throw error;
        }
    },

    /**
     * 流式响应处理工具函数（兼容混合格式）
     * @param {Response} response - fetch响应对象
     * @param {Function} onChunk - 数据块回调函数 (delta: string) => void
     * @param {Function} onComplete - 完成回调函数 (data: Object) => void
     * @param {Function} onError - 错误回调函数 (error: Error) => void
     */
    async handleStreamResponse(response, onChunk, onComplete, onError) {
        if (!response.ok) {
            const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
            if (onError) onError(error);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let sessionId = null;
        let messageId = null;
        let status = 'ask';
        let fullMessage = '';

        try {
            while (true) {
                const { done, value } = await reader.read();

                if (done) {
                    if (onComplete) {
                        onComplete({
                            session_id: sessionId,
                            message_id: messageId,
                            full_message: fullMessage,
                            status: status
                        });
                    }
                    break;
                }

                buffer += decoder.decode(value, { stream: true });

                // 尝试处理混合格式数据
                const jsonMatch = buffer.match(/^\{[^]*?\}(?=\S|$)/);

                if (jsonMatch) {
                    try {
                        const data = JSON.parse(jsonMatch[0]);

                        // 处理会话信息
                        if (data.session_id && data.message_id) {
                            sessionId = data.session_id;
                            messageId = data.message_id;
                            buffer = buffer.slice(jsonMatch[0].length);

                            // 如果JSON后面还有内容，作为文本处理
                            if (buffer.trim()) {
                                const textDelta = buffer;
                                fullMessage += textDelta;
                                if (onChunk) onChunk(textDelta);
                                buffer = '';
                            }
                            continue;
                        }

                        // 处理状态信息
                        if (data.status) {
                            status = data.status;
                            buffer = buffer.slice(jsonMatch[0].length);
                            continue;
                        }

                        // 处理delta字段
                        if (data.delta) {
                            fullMessage += data.delta;
                            if (onChunk) onChunk(data.delta);
                            buffer = buffer.slice(jsonMatch[0].length);
                            continue;
                        }

                        // 移除已处理的JSON
                        buffer = buffer.slice(jsonMatch[0].length);

                    } catch (parseError) {
                        // JSON解析失败，将整个缓冲区作为文本处理
                        console.warn('JSON解析失败，作为文本处理:', parseError);
                    }
                }

                // 处理剩余的文本内容
                if (buffer.trim()) {
                    fullMessage += buffer;
                    if (onChunk) onChunk(buffer);
                    buffer = '';
                }
            }
        } catch (error) {
            console.error('处理流式响应失败:', error);
            if (onError) {
                onError(error);
            }
        } finally {
            reader.releaseLock();
        }
    },

    /**
     * 更新AI回复消息内容
     * @param {Object} params - 请求参数
     * @param {number} params.document_id - 文档ID
     * @param {string} params.session_id - 会话ID
     * @param {string} params.message_id - 消息ID
     * @param {string} params.content - 更新的内容
     * @returns {Promise<Object>} 更新结果
     */
    async updateConversationMessage(params) {
        try {
            const response = await fetch('/project_document/conversation-messages/update', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.code === 200) {
                return result.data;
            } else {
                throw new Error(result.message || '更新AI回复失败');
            }
        } catch (error) {
            console.error('更新AI回复失败:', error);
            throw error;
        }
    },

    /**
     * 跳转到其他页面并传递参数
     * @param {string} pageUrl - 目标页面URL（相对路径或绝对路径）
     * @param {Object} params - 要传递的参数对象
     * @param {boolean} useSessionStorage - 是否使用sessionStorage存储（默认true）
     * @returns {void}
     */
    async navigateToPage(pageUrl, params = {}, useSessionStorage = true) {
        try {
            // 根据你的调用方式，提取可能需要的参数
            const {
                document_id,
                node_id,
                full_text,
                tree_data,
                ...otherParams
            } = params;

            // 统一参数名称，优先使用驼峰命名，但兼容下划线命名
            const documentId = params.documentId || document_id;
            const nodeId = params.node_id;
            const fullText = params.fullText || full_text;
            const treeData = params.tree_data || tree_data;

            if (useSessionStorage) {
                // 使用sessionStorage存储数据
                const storageKey = `page_nav_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                const navData = {
                    documentId,
                    nodeId,
                    fullText,
                    treeData,
                    ...otherParams,
                    timestamp: Date.now()
                };

                // 存储数据
                sessionStorage.setItem(storageKey, JSON.stringify(navData));

                // 将storage key作为URL参数传递
                const url = new URL(pageUrl, window.location.origin);
                url.searchParams.set('nav_key', storageKey);

                window.location.href = url.toString();
            } else {
                // 直接使用URL参数（注意：数据量大的话不适合）
                const url = new URL(pageUrl, window.location.origin);

                // 添加基本参数
                if (documentId) {
                    url.searchParams.set('document_id', documentId);
                }
                if (nodeId) {
                    url.searchParams.set('node_id', nodeId);
                }
                if (fullText && fullText.length < 1000) {
                    // 注意：full_text可能很大，只在小数据量时直接传递
                    url.searchParams.set('full_text', encodeURIComponent(fullText));
                }

                // 注意：treeData 可能很大，不适合直接放在URL中
                // 如果treeData较小，可以尝试序列化
                if (treeData && JSON.stringify(treeData).length < 2000) {
                    url.searchParams.set('tree_data', encodeURIComponent(JSON.stringify(treeData)));
                }

                // 添加其他参数
                Object.keys(otherParams).forEach(key => {
                    if (otherParams[key] !== undefined && otherParams[key] !== null) {
                        url.searchParams.set(key, otherParams[key]);
                    }
                });

                window.location.href = url.toString();
            }
        } catch (error) {
            console.error('跳转页面失败:', error);
            throw error;
        }
    },

    // 获取导航参数（更新以处理新的参数结构）
    getNavigationParams() {
        const urlParams = new URLSearchParams(window.location.search);
        const navKey = urlParams.get('nav_key');

        if (navKey) {
            const dataStr = sessionStorage.getItem(navKey);
            if (dataStr) {
                const data = JSON.parse(dataStr);
//                sessionStorage.removeItem(navKey);
                return data;
            }
        } else {
            // 从URL参数中直接获取
            const documentId = urlParams.get('document_id');
            const nodeId = urlParams.get('node_id');
            const fullText = urlParams.get('full_text');
            const treeDataStr = urlParams.get('tree_data');

            let treeData = null;
            if (treeDataStr) {
                try {
                    treeData = JSON.parse(decodeURIComponent(treeDataStr));
                } catch(e) {
                    console.error('解析tree_data失败', e);
                }
            }

            let fullTextDecoded = null;
            if (fullText) {
                try {
                    fullTextDecoded = decodeURIComponent(fullText);
                } catch(e) {
                    console.error('解码full_text失败', e);
                    fullTextDecoded = fullText;
                }
            }

            return {
                documentId,
                nodeId,
                fullText: fullTextDecoded,
                treeData,
                ...Object.fromEntries(urlParams.entries())
            };
        }
        return null;
    }

};

// 导出服务
window.ProjectDocumentService = ProjectDocumentService;