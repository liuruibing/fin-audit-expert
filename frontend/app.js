const { createApp } = Vue;

createApp({
  data() {
    return {
      currentTab: 'audit', // 'audit' | 'metrics'
      auditData: {
        filename: '加载中...',
        summary: { total_issues: 0, substantial_issues: 0, doubt_issues: 0, format_issues: 0 },
        issues: []
      },
      docPages: [],
      currentPage: 1,
      filterCategory: 'ALL', // 'ALL' | 'SUBSTANTIAL' | 'DOUBT' | 'FORMAT'
      selectedIssue: null,
      selectedSample: 'swlx',
      zoomScale: '1.0',

      // 模型底座引擎
      supportedModels: [
        { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash (OMP 内置底座)' },
        { id: 'qwen2.5-32b', name: 'Qwen2.5-32B-Instruct (私有化一体机)' },
        { id: 'harness-local', name: 'FinAudit Harness 确定性纪律引擎' }
      ],
      activeModelId: 'gemini-3.8-flash',
      
      // 价值回执
      metrics: {
        total_documents_audited: 6647,
        total_issues_flagged: 2967,
        substantial_defects_prevented: 253,
        expert_decisions_recorded: 0,
        confirmed_count: 0,
        false_alarm_count: 0,
        covered_institutions: 89
      },

      // 审核专家 Copilot
      showCopilot: true,
      copilotLoading: false,
      inputQuestion: '',
      quickQuestions: [
        '第 1 条为什么判为问题？',
        '这份报告里托管人全文一致吗？',
        '第 3 条份额加总勾稽算得对吗？'
      ],
      chatMessages: [
        {
          role: 'assistant',
          text: '您好！我是您的审核专家同事。当前已启用【Gemini 3.8 Flash】大模型作为审查底座，严格依照 Harness 框架纪律为您提供逐条带出处的金融审核服务。'
        }
      ],

      showBatchModal: false
    };
  },

  computed: {
    filteredIssues() {
      if (!this.auditData || !this.auditData.issues) return [];
      if (this.filterCategory === 'ALL') return this.auditData.issues;
      return this.auditData.issues.filter(i => i.category === this.filterCategory);
    },

    currentPageSpans() {
      if (!this.docPages || this.docPages.length === 0) return [];
      const pageObj = this.docPages.find(p => p.page === this.currentPage);
      return pageObj ? pageObj.spans : [];
    }
  },

  mounted() {
    this.fetchModels();
    this.fetchCurrentAudit();
    this.fetchMetrics();
  },
  methods: {
    async fetchCurrentAudit() {
      try {
        const res = await fetch('/api/audit/current');
        if (res.ok) {
          const data = await res.json();
          this.auditData = data.audit;
          this.docPages = data.doc_pages;
          if (this.auditData.issues && this.auditData.issues.length > 0) {
            this.focusIssue(this.auditData.issues[0]);
          }
        }
      } catch (e) {
        console.error('获取审核数据失败:', e);
      }
    },

    async fetchMetrics() {
      try {
        const res = await fetch('/api/metrics');
        if (res.ok) {
          this.metrics = await res.json();
        }
      } catch (e) {
        console.error('获取指标失败:', e);
      }
    },
    async fetchModels() {
      try {
        const res = await fetch('/api/models');
        if (res.ok) {
          const data = await res.json();
          this.supportedModels = data.models;
          this.activeModelId = data.active_model_id;
        }
      } catch (e) {
        console.error('获取模型配置失败:', e);
      }
    },

    async handleModelChange() {
      try {
        const res = await fetch('/api/models/select', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_id: this.activeModelId })
        });
        if (res.ok) {
          const data = await res.json();
          this.chatMessages.push({
            role: 'assistant',
            text: `[系统消息]: 模型底座已平滑切换为【${data.active_model_id}】。后续审核推理与对话问答将由该引擎驱动。`
          });
        }
      } catch (e) {
        console.error('切换模型失败:', e);
      }
    },

    async handleSampleChange() {
      try {
        const res = await fetch('/api/audit/switch-sample', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sample_name: this.selectedSample })
        });
        if (res.ok) {
          const data = await res.json();
          this.auditData = data.audit;
          this.docPages = data.doc_pages;
          this.currentPage = 1;
          if (this.auditData.issues && this.auditData.issues.length > 0) {
            this.focusIssue(this.auditData.issues[0]);
          }
        }
      } catch (e) {
        console.error('切换样本报告失败:', e);
      }
    },

    focusIssue(issue) {
      this.selectedIssue = issue;
      this.currentPage = issue.page;

      // 平滑滚动到对应页码的高亮区域
      this.$nextTick(() => {
        const highlightedEl = document.querySelector('.bg-amber-100');
        if (highlightedEl) {
          highlightedEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    },

    isSpanHighlighted(span) {
      if (!this.selectedIssue) return false;
      if (span.page !== this.selectedIssue.page) return false;
      const cleanSpan = span.text.replace(/\s+/g, '');
      const cleanQuote = this.selectedIssue.quote.replace(/\s+/g, '');
      return cleanSpan.includes(cleanQuote) || cleanQuote.includes(cleanSpan);
    },

    isSpanContext(span) {
      if (!this.selectedIssue || !this.selectedIssue.context_quote) return false;
      if (span.page !== this.selectedIssue.context_page) return false;
      const cleanSpan = span.text.replace(/\s+/g, '');
      const cleanContext = this.selectedIssue.context_quote.replace(/\s+/g, '');
      return cleanSpan.includes(cleanContext) || cleanContext.includes(cleanSpan);
    },

    getSeverityBadgeClass(severity) {
      if (severity === 'HIGH') return 'bg-rose-500/20 text-rose-300 border border-rose-500/30';
      if (severity === 'MEDIUM') return 'bg-amber-500/20 text-amber-300 border border-amber-500/30';
      return 'bg-blue-500/20 text-blue-300 border border-blue-500/30';
    },

    async makeDecision(issue, decision) {
      try {
        const res = await fetch('/api/decisions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            issue_id: issue.id,
            rule_id: issue.rule_id,
            decision: decision,
            expert_name: 'admin · 审核员',
            reason: decision === 'CONFIRMED_DEFECT' ? '经人工确认属于实质性表述/时点差错' : '经核对为合理业务例外',
            document_name: this.auditData.filename,
            quote: issue.quote
          })
        });

        if (res.ok) {
          issue.status = decision;
          this.fetchMetrics();
        }
      } catch (e) {
        console.error('裁决提交失败:', e);
      }
    },

    openCopilotForIssue(issue) {
      this.showCopilot = true;
      this.askCopilot(`为什么把第 ${issue.page} 页的“${issue.title}”判为问题？依据是什么？`);
    },

    async askCopilot(question) {
      if (!question || !question.trim()) return;
      const q = question.trim();
      this.inputQuestion = '';
      this.chatMessages.push({ role: 'user', text: q });
      this.copilotLoading = true;

      this.$nextTick(() => {
        if (this.$refs.chatList) {
          this.$refs.chatList.scrollTop = this.$refs.chatList.scrollHeight;
        }
      });

      try {
        const res = await fetch('/api/copilot/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: q,
            issue_id: this.selectedIssue ? this.selectedIssue.id : null
          })
        });

        if (res.ok) {
          const data = await res.json();
          this.chatMessages.push({ role: 'assistant', text: data.reply });
        } else {
          this.chatMessages.push({ role: 'assistant', text: '专家服务响应超时，请稍后重试。' });
        }
      } catch (e) {
        this.chatMessages.push({ role: 'assistant', text: '网络连接异常，无法连通审核专家服务。' });
      } finally {
        this.copilotLoading = false;
        this.$nextTick(() => {
          if (this.$refs.chatList) {
            this.$refs.chatList.scrollTop = this.$refs.chatList.scrollHeight;
          }
        });
      }
    },

    async handleFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch('/api/audit/upload', {
          method: 'POST',
          body: formData
        });

        if (res.ok) {
          await this.fetchCurrentAudit();
          alert('文档上传并审核完成！');
        }
      } catch (e) {
        alert('上传审核失败: ' + e);
      }
    },
    changePage(delta) {
      const target = this.currentPage + delta;
      if (target >= 1 && target <= this.docPages.length) {
        this.currentPage = target;
        this.$nextTick(() => {
          if (this.$refs.docViewport) {
            this.$refs.docViewport.scrollTop = 0;
          }
        });
      }
    },

    async runInlineDiagnosis(issue) {
      if (issue.diagnosis) {
        // 再次点击折叠
        issue.diagnosis = null;
        return;
      }
      issue.diagnosis = '专家正在秒级研判中...';
      try {
        const res = await fetch('/api/audit/diagnose', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: issue.title,
            description: issue.description,
            quote: issue.quote
          })
        });
        if (res.ok) {
          const data = await res.json();
          issue.diagnosis = data.analysis;
        } else {
          issue.diagnosis = '诊断超时，请重试。';
        }
      } catch (e) {
        issue.diagnosis = '分析失败，请检查网络。';
      }
    },
  }
}).mount('#app');
