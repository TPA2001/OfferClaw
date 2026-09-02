/**
 * 简历画像视图 — 用户画像编辑器
 * 多 Tab 编辑：基本信息 / 教育经历 / 工作经历 / 项目经历 / 技能 / 自我评价 / 证书 / 求职意向
 * 含完成度进度条、脏状态追踪、JSON 备份
 */
(function (global) {
    'use strict';

    const API = global.OfferCabinAPI;
    const Motion = global.OfferCabinMotion;
    const esc = API.esc.bind(API);

    // ============ 常量 ============

    const CSS_ID = 'profile-styles';

    const TABS = [
        { key: 'basic',        label: '基本信息' },
        { key: 'education',    label: '教育经历' },
        { key: 'experience',   label: '工作经历' },
        { key: 'projects',     label: '项目经历' },
        { key: 'skills',       label: '技能' },
        { key: 'languages',    label: '语言能力' },
        { key: 'certificates', label: '证书' },
        { key: 'awards',       label: '获奖荣誉' },
        { key: 'essays',       label: '开放题答案库' },
        { key: 'publications', label: '论文' },
        { key: 'patents',      label: '专利' },
        { key: 'summary',      label: '自我评价' },
        { key: 'job_intent',   label: '求职意向' },
        { key: 'custom',       label: '自定义字段' },
    ];

    const DEGREES = ['高中', '大专', '本科', '硕士', '博士'];
    const SKILL_LEVELS = ['了解', '熟悉', '掌握', '精通'];
    const SKILL_CATEGORIES = ['编程语言', '框架', '工具', '软技能'];
    const WORK_TYPES = ['全职', '兼职', '实习'];
    const AVAILABILITIES = ['随时', '一周内', '一个月内'];
    const GENDERS = ['男', '女'];
    // 央国企网申常见枚举
    const POLITICAL_STATUSES = ['中共党员', '中共预备党员', '共青团员', '群众', '民主党派'];
    const MARITAL_STATUSES = ['未婚', '已婚', '离异'];
    const HOUSEHOLD_TYPES = ['城镇户籍', '农村户籍'];
    const ETHNICITIES = ['汉族', '蒙古族', '满族', '朝鲜族', '回族', '壮族', '维吾尔族', '藏族', '苗族', '彝族', '其他'];
    // 教育经历：院校层次 & 教育形式（央国企常考）
    const SCHOOL_TYPES = ['985/双一流', '211/双一流', '重点大学', '普通本科', '海外院校', '专科院校'];
    const EDU_FORMS = ['全日制', '非全日制', '统招', '成人教育', '自学考试', '网络教育', '职业教育'];
    // 语言能力：熟练程度（网申常见枚举）
    const LANGUAGE_PROFICIENCIES = ['母语', '流利', '工作熟练', '中等', '基础'];
    const STUDY_MODES = ['统招', '非统招', '联合培养', '委托培养'];
    const GRADUATION_STATUSES = ['已毕业', '预计毕业', '在读', '肄业'];
    const EMPLOYMENT_TYPES = ['全职', '兼职', '实习', '合同', '自由职业'];
    const LOCATION_MODES = ['现场办公', '混合办公', '远程办公', '灵活'];
    const JOB_AVAILABILITIES = ['随时', '一周内', '一个月内', '两个月内', '三个月内'];
    // 获奖级别（网申常考）
    const AWARD_LEVELS = ['国家级', '省级', '市级', '校级', '院级', '企业级', '其他'];
    // 开放题答案版本标签（不同求职方向可存多版）
    const ESSAY_TAGS = ['互联网版', '国央企版', '外企英文版', '通用'];
    // 论文级别 / 作者角色
    const PUBLICATION_LEVELS = ['SCI', 'SSCI', 'EI', '中文核心', '普刊', '会议', '其他'];
    const PUBLICATION_ROLES = ['第一作者', '共同一作', '通讯作者', '参与', '其他'];
    // 专利类型 / 状态
    const PATENT_TYPES = ['发明专利', '实用新型', '外观设计', '软件著作权', '其他'];
    const PATENT_STATUSES = ['已授权', '实审中', '已申请'];

    const LEVEL_COLORS = {
        '了解': 'var(--ink-faint)',
        '熟悉': 'var(--olive)',
        '掌握': 'var(--olive-dark)',
        '精通': 'var(--terra)',
    };

    // ============ 状态 ============

    const state = {
        profile: null,
        completion: { overall: 0, sections: {} },
        activeTab: 'basic',
        dirty: false,
        loading: true,
        saving: false,
        error: null,
    };

    let root = null;
    let beforeUnloadHandler = null;

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.profile-view { padding-bottom: 4rem; }

/* --- 工具栏 --- */
.profile-toolbar {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.4rem;
    padding: 0.9rem 1.2rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    flex-wrap: wrap;
}
.completion-wrap {
    flex: 1;
    min-width: 200px;
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.completion-label {
    font-size: 0.78rem;
    color: var(--ink-soft);
    font-family: var(--font-mono);
    white-space: nowrap;
}
.completion-bar {
    flex: 1;
    height: 10px;
    background: var(--paper-deep);
    border-radius: 6px;
    overflow: hidden;
    position: relative;
}
.completion-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--olive), var(--olive-dark));
    border-radius: 6px;
    width: 0%;
    transition: width 0.8s var(--ease-out);
}
.completion-pct {
    font-family: var(--font-serif);
    font-size: 1.2rem;
    font-weight: 800;
    color: var(--olive-dark);
    min-width: 48px;
    text-align: right;
}
.save-status {
    font-size: 0.78rem;
    color: var(--ink-faint);
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    white-space: nowrap;
}
.save-status.dirty { color: var(--warn); font-weight: 600; }
.save-status.saved { color: var(--success); }
.save-status .status-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: currentColor;
}
.profile-toolbar .btn-save { flex-shrink: 0; }

/* --- Tab 面板 --- */
.tab-panels { min-height: 300px; }
.tab-panel { animation: profilePanelIn 0.3s var(--ease-out); }
@keyframes profilePanelIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}

/* --- 条目卡片（教育/工作/项目/证书） --- */
.entry-list {
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
}
.entry-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
    transition: box-shadow 0.2s var(--ease), border-color 0.2s var(--ease);
}
.entry-card:hover { box-shadow: var(--shadow-sm); border-color: var(--olive); }
.entry-card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.9rem;
    padding-bottom: 0.6rem;
    border-bottom: 1px dashed var(--line-soft);
}
.entry-card-title {
    font-family: var(--font-serif);
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.entry-card-index {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--olive);
    background: var(--olive-soft);
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
}
.entry-card-actions { display: flex; gap: 0.4rem; }
.entry-add-btn {
    margin-top: 0.9rem;
    width: 100%;
    padding: 0.7rem;
    border: 1px dashed var(--line);
    background: var(--paper-light);
    border-radius: 8px;
    font-size: 0.85rem;
    color: var(--ink-soft);
    cursor: pointer;
    transition: all 0.2s var(--ease);
    font-family: inherit;
}
.entry-add-btn:hover {
    border-color: var(--olive);
    color: var(--olive-dark);
    background: var(--olive-soft);
}

/* --- 技能编辑器 --- */
.skill-editor { display: flex; flex-direction: column; gap: 1rem; }
.skill-add-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
    padding: 0.8rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
}
.skill-add-input {
    flex: 1;
    min-width: 160px;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.88rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.skill-add-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: var(--card);
}
.skill-add-select {
    padding: 0.5rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.82rem;
    font-family: inherit;
    cursor: pointer;
}
.skill-add-select:focus { outline: none; border-color: var(--olive); }
.skill-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    min-height: 60px;
}
.skill-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.4rem 0.5rem 0.4rem 0.75rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    font-size: 0.82rem;
    transition: box-shadow 0.2s var(--ease), border-color 0.2s var(--ease);
}
.skill-chip:hover { box-shadow: var(--shadow-sm); border-color: var(--olive); }
.skill-chip-name { color: var(--ink); font-weight: 500; }
.skill-chip-level {
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.1rem 0.45rem;
    border-radius: 10px;
    color: var(--paper-light);
}
.skill-chip-cat {
    font-size: 0.68rem;
    color: var(--ink-faint);
    padding: 0.1rem 0.35rem;
    background: var(--paper-deep);
    border-radius: 8px;
}
.skill-chip-remove {
    background: none;
    border: none;
    color: var(--ink-faint);
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 0 0.2rem;
    transition: color 0.15s var(--ease);
}
.skill-chip-remove:hover { color: var(--danger); }

/* --- 标签编辑器 --- */
.tag-editor { display: flex; flex-direction: column; gap: 0.5rem; }
.tag-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    min-height: 36px;
    padding: 0.3rem 0;
}
.tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.4rem 0.3rem 0.65rem;
    background: var(--olive-soft);
    border: 1px solid var(--olive);
    border-radius: 16px;
    font-size: 0.8rem;
    color: var(--olive-dark);
    font-weight: 500;
}
.tag-chip-remove {
    background: none;
    border: none;
    color: var(--olive-dark);
    cursor: pointer;
    font-size: 0.95rem;
    line-height: 1;
    opacity: 0.6;
    transition: opacity 0.15s var(--ease);
}
.tag-chip-remove:hover { opacity: 1; color: var(--danger); }
.tag-add-input {
    padding: 0.45rem 0.7rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.85rem;
    font-family: inherit;
    flex: 1;
    min-width: 160px;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.tag-add-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: var(--card);
}

/* --- JSON 备份 --- */
.json-backup {
    margin-top: 1.8rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
}
.json-backup-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.8rem 1.2rem;
    border-bottom: 1px solid var(--line-soft);
    background: var(--paper-light);
}
.json-backup-title {
    font-family: var(--font-serif);
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--ink);
}
.json-backup-actions { display: flex; gap: 0.4rem; }
.json-backup pre {
    margin: 0;
    padding: 1rem 1.2rem;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    line-height: 1.55;
    color: var(--ink-soft);
    max-height: 360px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
}

/* --- 加载/错误态 --- */
.profile-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.8rem;
    padding: 3rem 1rem;
    color: var(--ink-faint);
    font-size: 0.88rem;
}

/* --- 分组分隔 / 自定义字段 / 敏感信息 --- */
.field-group-divider {
    width: 100%;
    margin: 0.6rem 0 0.2rem;
    padding-top: 0.8rem;
    border-top: 1px dashed var(--line-soft);
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--ink-soft);
    letter-spacing: 0.02em;
}
.form-field.full { grid-column: 1 / -1; }
.custom-hint {
    font-size: 0.8rem;
    color: var(--ink-soft);
    line-height: 1.6;
    margin: 0 0 0.9rem;
}
.sensitive-hint {
    background: var(--olive-soft);
    border: 1px solid var(--olive);
    border-radius: 8px;
    padding: 0.7rem 0.9rem;
    color: var(--olive-dark);
}
.custom-add-row {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
    padding: 0.8rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    margin-bottom: 0.9rem;
}
.custom-list { display: flex; flex-direction: column; gap: 0.6rem; }
.custom-row {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.6rem 0.9rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
}
.custom-key {
    font-weight: 700;
    color: var(--ink);
    min-width: 120px;
    font-size: 0.85rem;
}
.custom-val {
    flex: 1;
    color: var(--ink-soft);
    font-size: 0.85rem;
    word-break: break-all;
}
.empty-custom-hint {
    font-size: 0.8rem;
    color: var(--ink-faint);
    line-height: 1.6;
    margin: 0 0 0.6rem;
}
.section-custom-card {
    margin-top: 1.2rem;
    border-style: dashed;
}
.section-custom-card .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.card-badge {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--olive);
    background: var(--olive-soft);
    padding: 0.1rem 0.55rem;
    border-radius: 10px;
    white-space: nowrap;
}

/* --- 条目级自定义字段（记录卡片内部） --- */
.btn-xs {
    padding: 0.12rem 0.5rem;
    font-size: 0.72rem;
    border-radius: 5px;
}
.entry-custom-fields {
    margin-top: 0.8rem;
    padding-top: 0.7rem;
    border-top: 1px dashed var(--line-soft);
}
.entry-custom-head {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--ink-faint);
    margin-bottom: 0.6rem;
}
.entry-custom-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.6rem;
}
.entry-custom-row {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.7rem;
    background: var(--paper-light);
    border: 1px solid var(--line);
    border-radius: 7px;
}
.entry-custom-key {
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--olive-dark);
}
.entry-custom-val {
    font-size: 0.78rem;
    color: var(--ink-soft);
}
.entry-custom-add {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
}
.entry-custom-add .skill-add-input {
    flex: 1;
    min-width: 140px;
}

@media (max-width: 700px) {
    .profile-toolbar { flex-direction: column; align-items: stretch; }
    .completion-wrap { width: 100%; }
    .form-grid { grid-template-columns: 1fr; }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    function emptyProfile() {
        return {
            basic: {
                name: '', english_name: '', gender: '', age: '', birth: '', phone: '', email: '', location: '',
                ethnicity: '', political_status: '', marital_status: '', native_place: '',
                household_type: '', height: '', weight: '', health: '',
                wechat: '', qq: '', website: '', github: '', linkedin: '',
                english_level: '', driving_license: '', job_status: '', avatar: '', job_intent: '',
                current_company: '', current_title: '', years_of_experience: '',
                highest_education: '', available_date: ''
            },
            education: [],
            experience: [],
            projects: [],
            skills: [],
            summary: { self_intro: '', strengths: '', career_goal: '', expected_salary: '', expected_location: '', expected_position: '' },
            certificates: [],
            job_intent: { target_positions: [], target_cities: [], expected_salary: '', work_type: '', availability: '',
                          expected_industry: '', target_level: '', remote_preference: '',
                          willing_to_relocate: '', willing_to_travel: '', current_salary: '' },
            languages: [],
            awards: [],
            essays: [],
            publications: [],
            patents: [],
            extra_fields: {},
        };
    }

    function normalizeProfile(p) {
        if (!p || typeof p !== 'object') p = {};
        const base = emptyProfile();
        // 兼容后端 basic_info 字段名
        const basicSrc = (p.basic && typeof p.basic === 'object') ? p.basic
                       : (p.basic_info && typeof p.basic_info === 'object') ? p.basic_info : null;
        if (basicSrc) {
            base.basic = Object.assign(base.basic, basicSrc);
        }
        base.education = Array.isArray(p.education) ? p.education.map(normalizeEdu).filter(Boolean) : [];
        base.experience = Array.isArray(p.experience) ? p.experience.map(normalizeExp).filter(Boolean) : [];
        base.projects = Array.isArray(p.projects) ? p.projects.map(normalizeProj).filter(Boolean) : [];
        base.skills = normalizeSkills(p.skills);
        if (p.summary && typeof p.summary === 'object') {
            base.summary = Object.assign(base.summary, p.summary);
        }
        // 兼容后端 certifications 字段名
        const certSrc = Array.isArray(p.certificates) ? p.certificates
                      : (Array.isArray(p.certifications) ? p.certifications : []);
        base.certificates = certSrc.map(normalizeCert).filter(Boolean);
        if (p.job_intent && typeof p.job_intent === 'object') {
            base.job_intent = Object.assign(base.job_intent, p.job_intent);
            base.job_intent.target_positions = Array.isArray(base.job_intent.target_positions) ? base.job_intent.target_positions : [];
            base.job_intent.target_cities = Array.isArray(base.job_intent.target_cities) ? base.job_intent.target_cities : [];
        }
        // 兼容后端 languages 字段
        base.languages = Array.isArray(p.languages) ? p.languages.map(normalizeLang).filter(Boolean) : [];
        // 获奖/荣誉
        base.awards = Array.isArray(p.awards) ? p.awards.map(normalizeAward).filter(Boolean) : [];
        // 开放题答案库
        base.essays = Array.isArray(p.essays) ? p.essays.map(normalizeEssay).filter(Boolean) : [];
        // 论文/发表物
        base.publications = Array.isArray(p.publications) ? p.publications.map(normalizePublication).filter(Boolean) : [];
        // 专利
        base.patents = Array.isArray(p.patents) ? p.patents.map(normalizePatent).filter(Boolean) : [];
        // 自定义字段（用户添加的额外键值对）
        if (p.extra_fields && typeof p.extra_fields === 'object') {
            base.extra_fields = p.extra_fields;
        }
        return base;
    }

    function normalizeLang(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            name: e.name || '',
            proficiency: e.proficiency || '',
            test_score: e.test_score || '',
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizeAward(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            name: e.name || '',
            level: e.level || '',
            issuer: e.issuer || '',
            date: e.date || '',
            description: e.description || '',
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizeEssay(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            question: e.question || '',
            answer: e.answer || '',
            tag: e.tag || '',
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizePublication(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            title: e.title || '',
            venue: e.venue || '',
            level: e.level || '',
            authors: e.authors || '',
            role: e.role || '',
            date: e.date || '',
            doi: e.doi || '',
            description: e.description || '',
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizePatent(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            name: e.name || '',
            patent_no: e.patent_no || '',
            type: e.type || '',
            status: e.status || '',
            holder: e.holder || '',
            inventors: e.inventors || '',
            date: e.date || '',
            description: e.description || '',
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizeEdu(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            school: e.school || '',
            degree: e.degree || '',
            major: e.major || '',
            school_type: e.school_type || '',
            edu_form: e.edu_form || '',
            study_mode: e.study_mode || '',
            minor: e.minor || '',
            faculty: e.faculty || '',
            graduation_status: e.graduation_status || '',
            ranking: e.ranking || '',
            courses: e.courses || '',
            start_date: e.start_date || '',
            end_date: e.end_date || '',
            gpa: e.gpa || '',
            description: e.description || '',
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizeExp(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            company: e.company || '',
            position: e.position || '',
            department: e.department || '',
            industry: e.industry || '',
            city: e.city || '',
            employment_type: e.employment_type || '',
            location_mode: e.location_mode || '',
            team_size: e.team_size || '',
            is_current: e.is_current === true,
            technologies: e.technologies || '',
            start_date: e.start_date || '',
            end_date: e.end_date || '',
            description: e.description || '',
            achievements: Array.isArray(e.achievements) ? e.achievements :
                (typeof e.achievements === 'string' ? e.achievements : ''),
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizeProj(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            name: e.name || '',
            role: e.role || '',
            organization: e.organization || '',
            is_current: e.is_current === true,
            demo_url: e.demo_url || '',
            highlights: e.highlights || '',
            description: e.description || '',
            start_date: e.start_date || '',
            end_date: e.end_date || '',
            url: e.url || '',
            tech_stack: Array.isArray(e.tech_stack) ? e.tech_stack.join(', ') :
                (e.tech_stack || ''),
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizeCert(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            name: e.name || '',
            issuer: e.issuer || '',
            date: e.date || '',
            score: e.score || '',
            custom_fields: (e.custom_fields && typeof e.custom_fields === 'object') ? e.custom_fields : {},
        };
    }

    function normalizeSkills(skills) {
        if (!Array.isArray(skills)) return [];
        return skills.map(s => {
            if (typeof s === 'string') return { name: s, level: '熟悉', category: '' };
            return {
                name: s.name || '',
                level: s.level || '熟悉',
                category: s.category || '',
            };
        }).filter(s => s.name);
    }

    function markDirty() {
        if (!state.dirty) {
            state.dirty = true;
            updateSaveStatus();
        }
    }

    function achievementsToText(a) {
        if (Array.isArray(a)) return a.join('\n');
        return a || '';
    }

    function achievementsToArray(text) {
        return text.split('\n').map(s => s.trim()).filter(Boolean);
    }

    function techStackToText(ts) {
        if (Array.isArray(ts)) return ts.join(', ');
        return ts || '';
    }

    function techStackToArray(text) {
        return text.split(',').map(s => s.trim()).filter(Boolean);
    }

    // ============ 渲染：骨架 ============

    function renderShell() {
        const tabsHtml = TABS.map(t =>
            `<button class="tab ${t.key === state.activeTab ? 'active' : ''}" data-tab="${t.key}">${t.label}</button>`
        ).join('');

        return `
        <div class="view-container profile-view">
            <div class="view-header">
                <div class="header-eyebrow">PROFILE</div>
                <h1>简历画像</h1>
                <p>完善你的求职画像，Agent 将基于此生成简历与匹配岗位</p>
            </div>
            <div class="profile-toolbar">
                <div class="completion-wrap">
                    <span class="completion-label">完成度</span>
                    <div class="completion-bar">
                        <div class="completion-fill" id="completion-fill" style="width:0%"></div>
                    </div>
                    <span class="completion-pct" id="completion-pct">0%</span>
                </div>
                <span class="save-status" id="save-status">
                    <span class="status-dot"></span>
                    <span class="status-text">加载中...</span>
                </span>
                <input type="file" id="pdf-file-input" accept=".pdf,application/pdf" style="display:none">
                <button class="btn btn-ghost btn-import-pdf" id="btn-import-pdf" title="从 PDF 简历解析填充画像">导入 PDF</button>
                <button class="btn btn-primary btn-save" id="btn-save" disabled>保存</button>
            </div>
            <div class="tabs" id="profile-tabs">${tabsHtml}</div>
            <div class="tab-panels" id="tab-panels"></div>
            <div id="json-backup-container"></div>
        </div>`;
    }

    function renderLoading() {
        return `
        <div class="view-container profile-view">
            <div class="view-header">
                <div class="header-eyebrow">PROFILE</div>
                <h1>简历画像</h1>
                <p>完善你的求职画像，Agent 将基于此生成简历与匹配岗位</p>
            </div>
            <div class="profile-loading">
                <div class="spinner"></div>
                <span>正在加载画像数据...</span>
            </div>
        </div>`;
    }

    // ============ 渲染：工具栏状态 ============

    function updateSaveStatus() {
        const el = root.querySelector('#save-status');
        const btn = root.querySelector('#btn-save');
        if (!el || !btn) return;
        const text = el.querySelector('.status-text');
        if (state.saving) {
            el.className = 'save-status';
            text.textContent = '保存中...';
            btn.disabled = true;
            btn.textContent = '保存中...';
        } else if (state.dirty) {
            el.className = 'save-status dirty';
            text.textContent = '未保存';
            btn.disabled = false;
            btn.textContent = '保存';
        } else {
            el.className = 'save-status saved';
            text.textContent = '已保存';
            btn.disabled = false;
            btn.textContent = '保存';
        }
    }

    function updateCompletion() {
        const fill = root.querySelector('#completion-fill');
        const pct = root.querySelector('#completion-pct');
        // 后端 /profiles/completion 返回 percentage 字段；兼容旧字段 overall
        const overall = Math.max(0, Math.min(100,
            state.completion.percentage != null ? state.completion.percentage : (state.completion.overall || 0)));
        if (fill) fill.style.width = overall + '%';
        if (pct) {
            pct.textContent = overall + '%';
            if (Motion && Motion.countUp) {
                Motion.countUp(pct, overall, { duration: 800, suffix: '%' });
            }
        }
    }

    // ============ 渲染：Tab 面板 ============

    function renderTabPanel() {
        const container = root.querySelector('#tab-panels');
        if (!container) return;
        const tab = state.activeTab;
        let html = '';
        switch (tab) {
            case 'basic':        html = renderBasicTab(); break;
            case 'education':    html = renderEducationTab(); break;
            case 'experience':   html = renderExperienceTab(); break;
            case 'projects':     html = renderProjectsTab(); break;
            case 'skills':       html = renderSkillsTab(); break;
            case 'languages':    html = renderLanguagesTab(); break;
            case 'summary':      html = renderSummaryTab(); break;
            case 'certificates': html = renderCertificatesTab(); break;
            case 'awards':       html = renderAwardsTab(); break;
            case 'essays':       html = renderEssaysTab(); break;
            case 'publications': html = renderPublicationsTab(); break;
            case 'patents':      html = renderPatentsTab(); break;
            case 'job_intent':   html = renderJobIntentTab(); break;
            case 'custom':       html = renderCustomTab(); break;
        }
        // 对象型分类（单块表单）在底部追加「分类自定义字段」区块；
        // 列表型分类（教育/工作/项目/证书/获奖/开放题/论文/专利）的自定义字段在每个条目内部维护。
        if (tab !== 'education' && tab !== 'experience' && tab !== 'projects' && tab !== 'certificates'
            && tab !== 'awards' && tab !== 'essays' && tab !== 'publications' && tab !== 'patents') {
            html += renderSectionCustomFields(tab);
        }
        container.innerHTML = '<div class="tab-panel">' + html + '</div>';
        bindPanelEvents();
        if (Motion && Motion.tabEnter) {
            const panel = container.querySelector('.tab-panel');
            if (panel) Motion.tabEnter(panel);
        }
    }

    // --- 基本信息 ---

    function renderBasicTab() {
        const b = state.profile.basic;
        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">基本信息</h2>
            </div>
            <div class="form-grid">
                <div class="form-field">
                    <label>姓名</label>
                    <input type="text" data-section="basic" data-field="name" value="${esc(b.name)}" placeholder="你的姓名">
                </div>
                <div class="form-field">
                    <label>英文名</label>
                    <input type="text" data-section="basic" data-field="english_name" value="${esc(b.english_name)}" placeholder="如 San Zhang">
                </div>
                <div class="form-field">
                    <label>性别</label>
                    <select data-section="basic" data-field="gender">
                        <option value="">未设置</option>
                        ${GENDERS.map(g => `<option value="${g}" ${b.gender === g ? 'selected' : ''}>${g}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>年龄</label>
                    <input type="number" data-section="basic" data-field="age" value="${esc(b.age)}" placeholder="如 24" min="0" max="120">
                </div>
                <div class="form-field">
                    <label>手机号</label>
                    <input type="tel" data-section="basic" data-field="phone" value="${esc(b.phone)}" placeholder="11 位手机号">
                </div>
                <div class="form-field">
                    <label>邮箱</label>
                    <input type="email" data-section="basic" data-field="email" value="${esc(b.email)}" placeholder="your@email.com">
                </div>
                <div class="form-field">
                    <label>所在城市</label>
                    <input type="text" data-section="basic" data-field="location" value="${esc(b.location)}" placeholder="如 北京">
                </div>
                <div class="form-field">
                    <label>头像 URL</label>
                    <input type="url" data-section="basic" data-field="avatar" value="${esc(b.avatar)}" placeholder="https://...">
                </div>
                <div class="form-field">
                    <label>当前求职意向</label>
                    <input type="text" data-section="basic" data-field="job_intent" value="${esc(b.job_intent)}" placeholder="如 后端工程师">
                </div>
                <div class="form-field full">
                    <div class="field-group-divider">更多个人信息（同步至后端，便于网申自动填写）</div>
                </div>
                <div class="form-field">
                    <label>出生日期</label>
                    <input type="text" data-section="basic" data-field="birth" value="${esc(b.birth)}" placeholder="如 2000-01-15">
                </div>
                <div class="form-field">
                    <label>当前公司</label>
                    <input type="text" data-section="basic" data-field="current_company" value="${esc(b.current_company)}" placeholder="如 某科技公司">
                </div>
                <div class="form-field">
                    <label>当前职位</label>
                    <input type="text" data-section="basic" data-field="current_title" value="${esc(b.current_title)}" placeholder="如 高级后端工程师">
                </div>
                <div class="form-field">
                    <label>工作年限</label>
                    <input type="text" data-section="basic" data-field="years_of_experience" value="${esc(b.years_of_experience)}" placeholder="如 5">
                </div>
                <div class="form-field">
                    <label>最高学历</label>
                    <select data-section="basic" data-field="highest_education">
                        <option value="">请选择</option>
                        ${DEGREES.map(d => `<option value="${d}" ${b.highest_education === d ? 'selected' : ''}>${d}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>可入职日期</label>
                    <input type="text" data-section="basic" data-field="available_date" value="${esc(b.available_date)}" placeholder="如 2026-10-01">
                </div>
                <div class="form-field">
                    <label>民族</label>
                    <input type="text" data-section="basic" data-field="ethnicity" value="${esc(b.ethnicity)}" placeholder="如 汉族" list="ethnicity-options">
                    <datalist id="ethnicity-options">${ETHNICITIES.map(e => `<option value="${e}">`).join('')}</datalist>
                </div>
                <div class="form-field">
                    <label>政治面貌</label>
                    <select data-section="basic" data-field="political_status">
                        <option value="">请选择</option>
                        ${POLITICAL_STATUSES.map(ps => `<option value="${ps}" ${b.political_status === ps ? 'selected' : ''}>${ps}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>婚姻状况</label>
                    <select data-section="basic" data-field="marital_status">
                        <option value="">请选择</option>
                        ${MARITAL_STATUSES.map(ms => `<option value="${ms}" ${b.marital_status === ms ? 'selected' : ''}>${ms}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>籍贯</label>
                    <input type="text" data-section="basic" data-field="native_place" value="${esc(b.native_place)}" placeholder="如 山东济南">
                </div>
                <div class="form-field">
                    <label>户口类型</label>
                    <select data-section="basic" data-field="household_type">
                        <option value="">请选择</option>
                        ${HOUSEHOLD_TYPES.map(ht => `<option value="${ht}" ${b.household_type === ht ? 'selected' : ''}>${ht}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>身高 (cm)</label>
                    <input type="number" data-section="basic" data-field="height" value="${esc(b.height)}" placeholder="如 175" min="0" max="250">
                </div>
                <div class="form-field">
                    <label>体重 (kg)</label>
                    <input type="number" data-section="basic" data-field="weight" value="${esc(b.weight)}" placeholder="如 65" min="0" max="300">
                </div>
                <div class="form-field">
                    <label>健康状况</label>
                    <input type="text" data-section="basic" data-field="health" value="${esc(b.health)}" placeholder="如 健康 / 良好">
                </div>
                <div class="form-field">
                    <label>微信</label>
                    <input type="text" data-section="basic" data-field="wechat" value="${esc(b.wechat)}" placeholder="微信号">
                </div>
                <div class="form-field">
                    <label>QQ</label>
                    <input type="text" data-section="basic" data-field="qq" value="${esc(b.qq)}" placeholder="QQ 号">
                </div>
                <div class="form-field">
                    <label>个人网站 / 作品集</label>
                    <input type="url" data-section="basic" data-field="website" value="${esc(b.website)}" placeholder="https://...">
                </div>
                <div class="form-field">
                    <label>GitHub</label>
                    <input type="text" data-section="basic" data-field="github" value="${esc(b.github)}" placeholder="用户名">
                </div>
                <div class="form-field">
                    <label>领英 LinkedIn</label>
                    <input type="text" data-section="basic" data-field="linkedin" value="${esc(b.linkedin)}" placeholder="profile 链接或 ID">
                </div>
                <div class="form-field">
                    <label>英语水平</label>
                    <input type="text" data-section="basic" data-field="english_level" value="${esc(b.english_level)}" placeholder="如 CET-6 / 雅思 6.5">
                </div>
                <div class="form-field">
                    <label>驾照</label>
                    <input type="text" data-section="basic" data-field="driving_license" value="${esc(b.driving_license)}" placeholder="如 C1 / 无">
                </div>
                <div class="form-field">
                    <label>求职状态</label>
                    <input type="text" data-section="basic" data-field="job_status" value="${esc(b.job_status)}" placeholder="如 离职-随时到岗">
                </div>
            </div>
        </div>`;
    }

    // --- 教育经历 ---

    function renderEducationTab() {
        const list = state.profile.education;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">🎓</span><h3>暂无教育经历</h3><p>点击下方按钮添加第一条记录</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">教育经历 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="education" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>学校</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="school" value="${esc(e.school)}" placeholder="如 清华大学">
                        </div>
                        <div class="form-field">
                            <label>学历</label>
                            <select data-section="education" data-index="${i}" data-field="degree">
                                <option value="">请选择</option>
                                ${DEGREES.map(d => `<option value="${d}" ${e.degree === d ? 'selected' : ''}>${d}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>院校类型</label>
                            <select data-section="education" data-index="${i}" data-field="school_type">
                                <option value="">请选择</option>
                                ${SCHOOL_TYPES.map(st => `<option value="${st}" ${e.school_type === st ? 'selected' : ''}>${st}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>教育形式</label>
                            <select data-section="education" data-index="${i}" data-field="edu_form">
                                <option value="">请选择</option>
                                ${EDU_FORMS.map(ef => `<option value="${ef}" ${e.edu_form === ef ? 'selected' : ''}>${ef}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>培养方式</label>
                            <select data-section="education" data-index="${i}" data-field="study_mode">
                                <option value="">请选择</option>
                                ${STUDY_MODES.map(sm => `<option value="${sm}" ${e.study_mode === sm ? 'selected' : ''}>${sm}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>毕业状态</label>
                            <select data-section="education" data-index="${i}" data-field="graduation_status">
                                <option value="">请选择</option>
                                ${GRADUATION_STATUSES.map(gs => `<option value="${gs}" ${e.graduation_status === gs ? 'selected' : ''}>${gs}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>专业</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="major" value="${esc(e.major)}" placeholder="如 计算机科学">
                        </div>
                        <div class="form-field">
                            <label>辅修专业</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="minor" value="${esc(e.minor)}" placeholder="如 数学">
                        </div>
                        <div class="form-field">
                            <label>院系</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="faculty" value="${esc(e.faculty)}" placeholder="如 计算机学院">
                        </div>
                        <div class="form-field">
                            <label>GPA</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="gpa" value="${esc(e.gpa)}" placeholder="如 3.8/4.0">
                        </div>
                        <div class="form-field">
                            <label>专业排名</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="ranking" value="${esc(e.ranking)}" placeholder="如 前 10%">
                        </div>
                        <div class="form-field">
                            <label>开始时间</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="start_date" value="${esc(e.start_date)}" placeholder="如 2020-09">
                        </div>
                        <div class="form-field">
                            <label>结束时间</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="end_date" value="${esc(e.end_date)}" placeholder="如 2024-06 或 至今">
                        </div>
                        <div class="form-field full">
                            <label>主修课程</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="courses" value="${esc(e.courses)}" placeholder="如 数据结构、操作系统、计算机网络（逗号分隔）">
                        </div>
                        <div class="form-field full">
                            <label>描述</label>
                            <textarea data-section="education" data-index="${i}" data-field="description" placeholder="主修课程、学术成就、获得荣誉等">${esc(e.description)}</textarea>
                        </div>
                    </div>
                    ${renderEntryCustomFields('education', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="education">+ 添加教育经历</button>`;
        return html;
    }

    // --- 工作经历 ---

    function renderExperienceTab() {
        const list = state.profile.experience;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">💼</span><h3>暂无工作经历</h3><p>点击下方按钮添加第一条记录</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">工作经历 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="experience" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>公司</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="company" value="${esc(e.company)}" placeholder="如 字节跳动">
                        </div>
                        <div class="form-field">
                            <label>职位</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="position" value="${esc(e.position)}" placeholder="如 后端工程师">
                        </div>
                        <div class="form-field">
                            <label>部门</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="department" value="${esc(e.department)}" placeholder="如 平台研发部">
                        </div>
                        <div class="form-field">
                            <label>所属行业</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="industry" value="${esc(e.industry)}" placeholder="如 互联网 / 金融">
                        </div>
                        <div class="form-field">
                            <label>工作城市</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="city" value="${esc(e.city)}" placeholder="如 杭州">
                        </div>
                        <div class="form-field">
                            <label>雇佣类型</label>
                            <select data-section="experience" data-index="${i}" data-field="employment_type">
                                <option value="">请选择</option>
                                ${EMPLOYMENT_TYPES.map(et => `<option value="${et}" ${e.employment_type === et ? 'selected' : ''}>${et}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>办公方式</label>
                            <select data-section="experience" data-index="${i}" data-field="location_mode">
                                <option value="">请选择</option>
                                ${LOCATION_MODES.map(lm => `<option value="${lm}" ${e.location_mode === lm ? 'selected' : ''}>${lm}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>是否当前在职</label>
                            <select data-section="experience" data-index="${i}" data-field="is_current" data-type="bool">
                                <option value="false" ${e.is_current ? '' : 'selected'}>否</option>
                                <option value="true" ${e.is_current ? 'selected' : ''}>是</option>
                            </select>
                        </div>
                        <div class="form-field">
                            <label>开始时间</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="start_date" value="${esc(e.start_date)}" placeholder="如 2023-06">
                        </div>
                        <div class="form-field">
                            <label>结束时间</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="end_date" value="${esc(e.end_date)}" placeholder="如 2024-03 或 至今">
                        </div>
                        <div class="form-field full">
                            <label>使用技术</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="technologies" value="${esc(e.technologies)}" placeholder="如 Java、Redis、Kafka">
                        </div>
                        <div class="form-field full">
                            <label>工作描述</label>
                            <textarea data-section="experience" data-index="${i}" data-field="description" placeholder="工作职责与日常内容">${esc(e.description)}</textarea>
                        </div>
                        <div class="form-field full">
                            <label>主要成就（每行一条）</label>
                            <textarea data-section="experience" data-index="${i}" data-field="achievements" data-type="text-array" placeholder="每行一条成就，如：&#10;优化了 XX 接口性能提升 50%&#10;主导了 XX 项目的从 0 到 1">${esc(achievementsToText(e.achievements))}</textarea>
                        </div>
                    </div>
                    ${renderEntryCustomFields('experience', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="experience">+ 添加工作经历</button>`;
        return html;
    }

    // --- 项目经历 ---

    function renderProjectsTab() {
        const list = state.profile.projects;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">📦</span><h3>暂无项目经历</h3><p>点击下方按钮添加第一条记录</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">项目经历 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="projects" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>项目名称</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="name" value="${esc(e.name)}" placeholder="如 OfferCabin 求职助手">
                        </div>
                        <div class="form-field">
                            <label>角色</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="role" value="${esc(e.role)}" placeholder="如 全栈开发 / 负责人">
                        </div>
                        <div class="form-field">
                            <label>所属组织</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="organization" value="${esc(e.organization)}" placeholder="如 学校实验室 / 个人项目">
                        </div>
                        <div class="form-field">
                            <label>是否进行中</label>
                            <select data-section="projects" data-index="${i}" data-field="is_current" data-type="bool">
                                <option value="false" ${e.is_current ? '' : 'selected'}>否</option>
                                <option value="true" ${e.is_current ? 'selected' : ''}>是</option>
                            </select>
                        </div>
                        <div class="form-field">
                            <label>开始时间</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="start_date" value="${esc(e.start_date)}" placeholder="如 2024-01">
                        </div>
                        <div class="form-field">
                            <label>结束时间</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="end_date" value="${esc(e.end_date)}" placeholder="如 2024-06 或 至今">
                        </div>
                        <div class="form-field full">
                            <label>项目链接</label>
                            <input type="url" data-section="projects" data-index="${i}" data-field="url" value="${esc(e.url)}" placeholder="https://github.com/...">
                        </div>
                        <div class="form-field full">
                            <label>演示链接</label>
                            <input type="url" data-section="projects" data-index="${i}" data-field="demo_url" value="${esc(e.demo_url)}" placeholder="https://demo.example.com">
                        </div>
                        <div class="form-field full">
                            <label>技术栈（逗号分隔）</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="tech_stack" data-type="csv-array" value="${esc(techStackToText(e.tech_stack))}" placeholder="如 Python, FastAPI, React">
                        </div>
                        <div class="form-field full">
                            <label>项目亮点</label>
                            <textarea data-section="projects" data-index="${i}" data-field="highlights" placeholder="效果、指标、架构亮点">${esc(e.highlights)}</textarea>
                        </div>
                        <div class="form-field full">
                            <label>项目描述</label>
                            <textarea data-section="projects" data-index="${i}" data-field="description" placeholder="项目背景、你的贡献、技术亮点">${esc(e.description)}</textarea>
                        </div>
                    </div>
                    ${renderEntryCustomFields('projects', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="projects">+ 添加项目经历</button>`;
        return html;
    }

    // --- 技能 ---

    function renderSkillsTab() {
        const skills = state.profile.skills;
        let chipsHtml = '';
        if (skills.length === 0) {
            chipsHtml = '<span style="color:var(--ink-faint);font-size:0.85rem;padding:0.5rem 0">暂未添加技能，在上方输入后按回车添加</span>';
        } else {
            chipsHtml = skills.map((s, i) => {
                const lvl = s.level || '熟悉';
                const lvlColor = LEVEL_COLORS[lvl] || 'var(--olive)';
                return `
                <div class="skill-chip">
                    <span class="skill-chip-name">${esc(s.name)}</span>
                    <span class="skill-chip-level" style="background:${lvlColor}">${esc(lvl)}</span>
                    ${s.category ? `<span class="skill-chip-cat">${esc(s.category)}</span>` : ''}
                    <button class="skill-chip-remove" data-action="delete-skill" data-index="${i}" title="删除">×</button>
                </div>`;
            }).join('');
        }

        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">技能管理</h2>
            </div>
            <div class="skill-editor">
                <div class="skill-add-row">
                    <input type="text" class="skill-add-input" id="skill-name-input" placeholder="输入技能名称，如 Python，按回车添加">
                    <select class="skill-add-select" id="skill-level-select">
                        ${SKILL_LEVELS.map(l => `<option value="${l}">${l}</option>`).join('')}
                    </select>
                    <select class="skill-add-select" id="skill-category-select">
                        ${SKILL_CATEGORIES.map(c => `<option value="${c}">${c}</option>`).join('')}
                    </select>
                    <button class="btn btn-primary btn-sm" id="skill-add-btn">添加技能</button>
                </div>
                <div class="skill-chips" id="skill-chips">${chipsHtml}</div>
            </div>
        </div>`;
    }

    // --- 语言能力 ---

    function renderLanguagesTab() {
        const list = state.profile.languages;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">🌐</span><h3>暂无语言能力</h3><p>添加你的语种与熟练程度，如 英语 / CET-6</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">语言 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="languages" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>语种</label>
                            <input type="text" data-section="languages" data-index="${i}" data-field="name" value="${esc(e.name)}" placeholder="如 英语 / 日语">
                        </div>
                        <div class="form-field">
                            <label>熟练程度</label>
                            <select data-section="languages" data-index="${i}" data-field="proficiency">
                                <option value="">请选择</option>
                                ${LANGUAGE_PROFICIENCIES.map(p => `<option value="${p}" ${e.proficiency === p ? 'selected' : ''}>${p}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>考试成绩 / 证书</label>
                            <input type="text" data-section="languages" data-index="${i}" data-field="test_score" value="${esc(e.test_score)}" placeholder="如 CET-6 / 雅思 7.0">
                        </div>
                    </div>
                    ${renderEntryCustomFields('languages', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="languages">+ 添加语言</button>`;
        return html;
    }

    // --- 获奖荣誉 ---

    function renderAwardsTab() {
        const list = state.profile.awards;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">🏆</span><h3>暂无获奖荣誉</h3><p>添加奖学金、竞赛、荣誉称号等，网申常考（注意区分于证书）</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">获奖 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="awards" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>奖项名称</label>
                            <input type="text" data-section="awards" data-index="${i}" data-field="name" value="${esc(e.name)}" placeholder="如 校级一等奖学金">
                        </div>
                        <div class="form-field">
                            <label>获奖级别</label>
                            <select data-section="awards" data-index="${i}" data-field="level">
                                <option value="">请选择</option>
                                ${AWARD_LEVELS.map(l => `<option value="${l}" ${e.level === l ? 'selected' : ''}>${l}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>颁发单位</label>
                            <input type="text" data-section="awards" data-index="${i}" data-field="issuer" value="${esc(e.issuer)}" placeholder="如 XX大学 / 教育部">
                        </div>
                        <div class="form-field">
                            <label>获奖时间</label>
                            <input type="text" data-section="awards" data-index="${i}" data-field="date" value="${esc(e.date)}" placeholder="如 2023-06">
                        </div>
                        <div class="form-field full">
                            <label>备注 / 描述</label>
                            <textarea data-section="awards" data-index="${i}" data-field="description" rows="2" placeholder="如 专业成绩前 5%">${esc(e.description)}</textarea>
                        </div>
                    </div>
                    ${renderEntryCustomFields('awards', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="awards">+ 添加获奖</button>`;
        return html;
    }

    // --- 开放题答案库 ---

    function renderEssaysTab() {
        const list = state.profile.essays;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">💬</span><h3>暂无开放题答案</h3><p>提前写好「为什么选择我们公司」「职业规划」等网申常问开放题，可存多个版本（互联网版 / 国央企版 / 外企英文版）</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">开放题 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="essays" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field full">
                            <label>问题</label>
                            <input type="text" data-section="essays" data-index="${i}" data-field="question" value="${esc(e.question)}" placeholder="如 为什么选择我们公司">
                        </div>
                        <div class="form-field full">
                            <label>答案</label>
                            <textarea data-section="essays" data-index="${i}" data-field="answer" rows="4" placeholder="提前撰写、可复用的回答">${esc(e.answer)}</textarea>
                        </div>
                        <div class="form-field">
                            <label>版本标签</label>
                            <select data-section="essays" data-index="${i}" data-field="tag">
                                <option value="">请选择</option>
                                ${ESSAY_TAGS.map(t => `<option value="${t}" ${e.tag === t ? 'selected' : ''}>${t}</option>`).join('')}
                            </select>
                        </div>
                    </div>
                    ${renderEntryCustomFields('essays', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="essays">+ 添加开放题答案</button>`;
        return html;
    }

    // --- 论文 / 发表物 ---

    function renderPublicationsTab() {
        const list = state.profile.publications;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">📄</span><h3>暂无论文</h3><p>添加发表的论文（SCI / EI / 中文核心 / 普刊 / 会议），校招与科研岗常考</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">论文 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="publications" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field full">
                            <label>论文题目</label>
                            <input type="text" data-section="publications" data-index="${i}" data-field="title" value="${esc(e.title)}" placeholder="如 基于深度学习的推荐系统研究">
                        </div>
                        <div class="form-field full">
                            <label>期刊 / 会议</label>
                            <input type="text" data-section="publications" data-index="${i}" data-field="venue" value="${esc(e.venue)}" placeholder="如 计算机学报 / AAAI 2023">
                        </div>
                        <div class="form-field">
                            <label>级别</label>
                            <select data-section="publications" data-index="${i}" data-field="level">
                                <option value="">请选择</option>
                                ${PUBLICATION_LEVELS.map(l => `<option value="${l}" ${e.level === l ? 'selected' : ''}>${l}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>本人角色</label>
                            <select data-section="publications" data-index="${i}" data-field="role">
                                <option value="">请选择</option>
                                ${PUBLICATION_ROLES.map(r => `<option value="${r}" ${e.role === r ? 'selected' : ''}>${r}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>发表时间</label>
                            <input type="text" data-section="publications" data-index="${i}" data-field="date" value="${esc(e.date)}" placeholder="如 2023-06">
                        </div>
                        <div class="form-field">
                            <label>DOI / 链接</label>
                            <input type="text" data-section="publications" data-index="${i}" data-field="doi" value="${esc(e.doi)}" placeholder="如 10.1234/xxxx">
                        </div>
                        <div class="form-field full">
                            <label>作者</label>
                            <input type="text" data-section="publications" data-index="${i}" data-field="authors" value="${esc(e.authors)}" placeholder="如 张三(第一作者), 李四">
                        </div>
                        <div class="form-field full">
                            <label>备注 / 摘要</label>
                            <textarea data-section="publications" data-index="${i}" data-field="description" rows="2" placeholder="简述研究内容与成果">${esc(e.description)}</textarea>
                        </div>
                    </div>
                    ${renderEntryCustomFields('publications', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="publications">+ 添加论文</button>`;
        return html;
    }

    // --- 专利 ---

    function renderPatentsTab() {
        const list = state.profile.patents;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">⚙️</span><h3>暂无专利</h3><p>添加已申请 / 已授权的专利（发明专利 / 实用新型 / 软著）</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">专利 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="patents" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field full">
                            <label>专利名称</label>
                            <input type="text" data-section="patents" data-index="${i}" data-field="name" value="${esc(e.name)}" placeholder="如 一种数据处理方法及装置">
                        </div>
                        <div class="form-field">
                            <label>专利号 / 申请号</label>
                            <input type="text" data-section="patents" data-index="${i}" data-field="patent_no" value="${esc(e.patent_no)}" placeholder="如 CN202310123456.7">
                        </div>
                        <div class="form-field">
                            <label>类型</label>
                            <select data-section="patents" data-index="${i}" data-field="type">
                                <option value="">请选择</option>
                                ${PATENT_TYPES.map(t => `<option value="${t}" ${e.type === t ? 'selected' : ''}>${t}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>状态</label>
                            <select data-section="patents" data-index="${i}" data-field="status">
                                <option value="">请选择</option>
                                ${PATENT_STATUSES.map(s => `<option value="${s}" ${e.status === s ? 'selected' : ''}>${s}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>时间</label>
                            <input type="text" data-section="patents" data-index="${i}" data-field="date" value="${esc(e.date)}" placeholder="申请/授权时间，如 2023-06">
                        </div>
                        <div class="form-field">
                            <label>申请人</label>
                            <input type="text" data-section="patents" data-index="${i}" data-field="holder" value="${esc(e.holder)}" placeholder="如 XX大学">
                        </div>
                        <div class="form-field full">
                            <label>发明人</label>
                            <input type="text" data-section="patents" data-index="${i}" data-field="inventors" value="${esc(e.inventors)}" placeholder="发明人（含本人）">
                        </div>
                        <div class="form-field full">
                            <label>备注</label>
                            <textarea data-section="patents" data-index="${i}" data-field="description" rows="2" placeholder="简述专利内容">${esc(e.description)}</textarea>
                        </div>
                    </div>
                    ${renderEntryCustomFields('patents', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="patents">+ 添加专利</button>`;
        return html;
    }

    // --- 自我评价 ---

    function renderSummaryTab() {
        const s = state.profile.summary;
        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">自我评价</h2>
            </div>
            <div class="form-grid">
                <div class="form-field full">
                    <label>自我介绍</label>
                    <textarea data-section="summary" data-field="self_intro" rows="4" placeholder="一段简短的自我介绍，让 HR 快速了解你">${esc(s.self_intro)}</textarea>
                </div>
                <div class="form-field full">
                    <label>核心优势（每行一条）</label>
                    <textarea data-section="summary" data-field="strengths" rows="4" placeholder="你的核心竞争力，如：&#10;扎实的算法与数据结构基础&#10;3 年后端开发经验">${esc(s.strengths)}</textarea>
                </div>
                <div class="form-field full">
                    <label>职业目标</label>
                    <textarea data-section="summary" data-field="career_goal" rows="3" placeholder="你的中长期职业规划">${esc(s.career_goal)}</textarea>
                </div>
                <div class="form-field">
                    <label>期望薪资</label>
                    <input type="text" data-section="summary" data-field="expected_salary" value="${esc(s.expected_salary)}" placeholder="如 20-30K">
                </div>
                <div class="form-field">
                    <label>期望城市</label>
                    <input type="text" data-section="summary" data-field="expected_location" value="${esc(s.expected_location)}" placeholder="如 北京/上海">
                </div>
                <div class="form-field">
                    <label>期望职位</label>
                    <input type="text" data-section="summary" data-field="expected_position" value="${esc(s.expected_position)}" placeholder="如 高级后端工程师">
                </div>
            </div>
        </div>`;
    }

    // --- 证书 ---

    function renderCertificatesTab() {
        const list = state.profile.certificates;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">📜</span><h3>暂无证书</h3><p>点击下方按钮添加你的证书</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">证书 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="certificates" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>证书名称</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="name" value="${esc(e.name)}" placeholder="如 软件设计师">
                        </div>
                        <div class="form-field">
                            <label>颁发机构</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="issuer" value="${esc(e.issuer)}" placeholder="如 工信部">
                        </div>
                        <div class="form-field">
                            <label>获得日期</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="date" value="${esc(e.date)}" placeholder="如 2023-06">
                        </div>
                        <div class="form-field">
                            <label>成绩/分数</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="score" value="${esc(e.score)}" placeholder="如 优秀 / 90">
                        </div>
                    </div>
                    ${renderEntryCustomFields('certificates', e, i)}
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="certificates">+ 添加证书</button>`;
        return html;
    }

    // --- 求职意向 ---

    function renderJobIntentTab() {
        const j = state.profile.job_intent;
        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">求职意向</h2>
            </div>
            <div class="form-grid">
                <div class="form-field full">
                    <label>目标职位</label>
                    <div class="tag-editor">
                        <div class="tag-chips" id="tag-positions">
                            ${(j.target_positions || []).map((p, i) =>
                                `<div class="tag-chip"><span>${esc(p)}</span><button class="tag-chip-remove" data-action="delete-tag" data-field="target_positions" data-index="${i}" title="删除">×</button></div>`
                            ).join('')}
                        </div>
                        <input type="text" class="tag-add-input" id="input-positions" placeholder="输入职位后按回车添加，如 后端工程师" data-field="target_positions">
                    </div>
                </div>
                <div class="form-field full">
                    <label>目标城市</label>
                    <div class="tag-editor">
                        <div class="tag-chips" id="tag-cities">
                            ${(j.target_cities || []).map((c, i) =>
                                `<div class="tag-chip"><span>${esc(c)}</span><button class="tag-chip-remove" data-action="delete-tag" data-field="target_cities" data-index="${i}" title="删除">×</button></div>`
                            ).join('')}
                        </div>
                        <input type="text" class="tag-add-input" id="input-cities" placeholder="输入城市后按回车添加，如 北京" data-field="target_cities">
                    </div>
                </div>
                <div class="form-field">
                    <label>期望薪资</label>
                    <input type="text" data-section="job_intent" data-field="expected_salary" value="${esc(j.expected_salary)}" placeholder="如 20-30K">
                </div>
                <div class="form-field">
                    <label>工作类型</label>
                    <select data-section="job_intent" data-field="work_type">
                        <option value="">请选择</option>
                        ${WORK_TYPES.map(w => `<option value="${w}" ${j.work_type === w ? 'selected' : ''}>${w}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>到岗时间</label>
                    <select data-section="job_intent" data-field="availability">
                        <option value="">请选择</option>
                        ${AVAILABILITIES.map(a => `<option value="${a}" ${j.availability === a ? 'selected' : ''}>${a}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>期望行业</label>
                    <input type="text" data-section="job_intent" data-field="expected_industry" value="${esc(j.expected_industry)}" placeholder="如 AI / SaaS / 电商">
                </div>
                <div class="form-field">
                    <label>目标级别</label>
                    <input type="text" data-section="job_intent" data-field="target_level" value="${esc(j.target_level)}" placeholder="如 高级 / 专家">
                </div>
                <div class="form-field">
                    <label>办公方式偏好</label>
                    <select data-section="job_intent" data-field="remote_preference">
                        <option value="">请选择</option>
                        ${LOCATION_MODES.map(m => `<option value="${m}" ${j.remote_preference === m ? 'selected' : ''}>${m}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>是否接受异地</label>
                    <select data-section="job_intent" data-field="willing_to_relocate">
                        <option value="">请选择</option>
                        <option value="是" ${j.willing_to_relocate === '是' ? 'selected' : ''}>是</option>
                        <option value="否" ${j.willing_to_relocate === '否' ? 'selected' : ''}>否</option>
                    </select>
                </div>
                <div class="form-field">
                    <label>是否接受出差</label>
                    <select data-section="job_intent" data-field="willing_to_travel">
                        <option value="">请选择</option>
                        <option value="是" ${j.willing_to_travel === '是' ? 'selected' : ''}>是</option>
                        <option value="否" ${j.willing_to_travel === '否' ? 'selected' : ''}>否</option>
                    </select>
                </div>
                <div class="form-field">
                    <label>当前薪资</label>
                    <input type="text" data-section="job_intent" data-field="current_salary" value="${esc(j.current_salary)}" placeholder="如 20-30K">
                </div>
            </div>
        </div>`;
    }

    // --- 自定义字段 ---
    // 用户可添加任意「字段名 → 值」，用于覆盖标准画像未列举的信息
    // 注：身份证号、家庭住址、银行卡、护照、紧急联系人等敏感字段一律不采集、不存储
    //    （前端不提供入口，后端 sanitizer 也会兜底剔除）

    // --- 分类内自定义字段（每个标签页底部统一区块） ---

    const SECTION_CUSTOM_LABELS = {
        basic: '基本信息',
        education: '教育经历',
        experience: '工作经历',
        projects: '项目经历',
        skills: '技能',
        summary: '自我评价',
        certificates: '证书',
        job_intent: '求职意向',
    };

    // 匹配「分类:字段名」格式的 key（分类内自定义字段的前缀）
    const SECTION_PREFIX_RE = /^basic:|^education:|^experience:|^projects:|^skills:|^summary:|^certificates:|^job_intent:/;

    /** 从 extra_fields 中取某分类下已添加的自定义字段（key 带 `section:` 前缀以隔离分类） */
    function sectionCustomOf(section) {
        const extra = state.profile.extra_fields || {};
        const prefix = section + ':';
        const out = {};
        Object.keys(extra).forEach((k) => {
            if (k.indexOf(prefix) === 0) out[k.slice(prefix.length)] = extra[k];
        });
        return out;
    }

    function renderSectionCustomFields(section) {
        const label = SECTION_CUSTOM_LABELS[section];
        if (!label) return '';
        const custom = sectionCustomOf(section);
        const keys = Object.keys(custom);
        let rows = '';
        if (keys.length === 0) {
            rows = '<p class="empty-custom-hint">本分类暂无自定义字段。可添加该分类下未内置的网申字段，例如：奖惩情况、实习单位性质等。</p>';
        } else {
            rows = keys.map((k) =>
                `<div class="custom-row">
                    <div class="custom-key">${esc(k)}</div>
                    <div class="custom-val">${esc(custom[k])}</div>
                    <button class="btn btn-danger btn-sm" data-action="delete-section-custom" data-section="${section}" data-key="${esc(k)}">删除</button>
                </div>`
            ).join('');
        }
        return `
        <div class="card section-custom-card">
            <div class="card-header">
                <h2 class="card-title">${label} · 自定义字段</h2>
                <span class="card-badge">按需补充</span>
            </div>
            <p class="custom-hint">这些字段仅作用于「${label}」分类，会同步到后端并按字段名自动匹配网申表单。</p>
            <div class="custom-add-row">
                <input type="text" id="sec-custom-key-${section}" class="skill-add-input" placeholder="字段名，如：奖惩情况">
                <input type="text" id="sec-custom-val-${section}" class="skill-add-input" placeholder="字段值，如：校级三好学生">
                <button class="btn btn-primary btn-sm" data-action="add-section-custom" data-section="${section}">添加</button>
            </div>
            <div class="custom-list">${rows}</div>
        </div>`;
    }

    function addSectionCustomField(section) {
        const keyEl = root.querySelector('#sec-custom-key-' + section);
        const valEl = root.querySelector('#sec-custom-val-' + section);
        if (!keyEl || !valEl) return;
        const key = keyEl.value.trim();
        const val = valEl.value.trim();
        if (!key) { API.toast('请填写字段名', 'warn'); return; }
        if (!state.profile.extra_fields) state.profile.extra_fields = {};
        const fullKey = section + ':' + key;
        if (Object.prototype.hasOwnProperty.call(state.profile.extra_fields, fullKey)) {
            API.toast('该字段名已在此分类下存在', 'warn'); return;
        }
        state.profile.extra_fields[fullKey] = val;
        markDirty();
        renderTabPanel();
        API.toast('已添加自定义字段', 'info', 1200);
    }

    function deleteSectionCustomField(section, key) {
        if (!state.profile.extra_fields) return;
        delete state.profile.extra_fields[section + ':' + key];
        markDirty();
        renderTabPanel();
        API.toast('已删除', 'success', 1200);
    }

    // --- 条目级自定义字段（教育/工作/项目/证书 的单条记录内部） ---

    /** 渲染单条记录内部的「该条目的自定义字段」区块 */
    function renderEntryCustomFields(section, entry, index) {
        const cf = (entry && entry.custom_fields && typeof entry.custom_fields === 'object') ? entry.custom_fields : {};
        const keys = Object.keys(cf);
        let rows = '';
        if (keys.length > 0) {
            rows = keys.map((k) =>
                `<div class="entry-custom-row">
                    <span class="entry-custom-key">${esc(k)}</span>
                    <span class="entry-custom-val">${esc(cf[k])}</span>
                    <button class="btn btn-danger btn-xs" data-action="delete-entry-custom" data-section="${section}" data-index="${index}" data-key="${esc(k)}">删除</button>
                </div>`
            ).join('');
        }
        return `
        <div class="entry-custom-fields">
            <div class="entry-custom-head">该条目的自定义字段</div>
            <div class="entry-custom-list">${rows}</div>
            <div class="entry-custom-add">
                <input type="text" id="ecf-key-${section}-${index}" class="skill-add-input" placeholder="字段名，如：学院 / 奖惩情况">
                <input type="text" id="ecf-val-${section}-${index}" class="skill-add-input" placeholder="字段值">
                <button class="btn btn-ghost btn-xs" data-action="add-entry-custom" data-section="${section}" data-index="${index}">添加</button>
            </div>
        </div>`;
    }

    function addEntryCustomField(section, index) {
        const item = state.profile[section] && state.profile[section][index];
        if (!item) return;
        const keyEl = root.querySelector('#ecf-key-' + section + '-' + index);
        const valEl = root.querySelector('#ecf-val-' + section + '-' + index);
        if (!keyEl || !valEl) return;
        const key = keyEl.value.trim();
        const val = valEl.value.trim();
        if (!key) { API.toast('请填写字段名', 'warn'); return; }
        if (!item.custom_fields || typeof item.custom_fields !== 'object') item.custom_fields = {};
        if (Object.prototype.hasOwnProperty.call(item.custom_fields, key)) {
            API.toast('该字段已在此条目存在', 'warn'); return;
        }
        item.custom_fields[key] = val;
        markDirty();
        renderTabPanel();
        API.toast('已在条目内添加字段', 'info', 1200);
    }

    function deleteEntryCustomField(section, index, key) {
        const item = state.profile[section] && state.profile[section][index];
        if (!item || !item.custom_fields) return;
        delete item.custom_fields[key];
        markDirty();
        renderTabPanel();
        API.toast('已删除', 'success', 1200);
    }

    function renderCustomTab() {
        // 仅展示不带「分类:」前缀的全局自定义字段；各分类内的字段在各标签页底部管理
        const extra = state.profile.extra_fields || {};
        const keys = Object.keys(extra).filter((k) => !SECTION_PREFIX_RE.test(k));
        let rows = '';
        if (keys.length === 0) {
            rows = '<div class="empty-card"><span class="empty-emoji">🧩</span><h3>暂无全局自定义字段</h3><p>添加任意「字段名 → 值」，例如：党员转正时间 → 2022-07、外语能力 → 日语 N2。填表时会按字段名自动匹配网申表单。</p><p>如需在特定分类下补充字段，请切换到对应标签页，在底部「分类 · 自定义字段」区域添加。</p></div>';
        } else {
            rows = keys.map((k) =>
                `<div class="custom-row">
                    <div class="custom-key">${esc(k)}</div>
                    <div class="custom-val">${esc(extra[k])}</div>
                    <button class="btn btn-danger btn-sm" data-action="delete-custom" data-key="${esc(k)}">删除</button>
                </div>`
            ).join('');
        }
        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">全局自定义字段</h2>
            </div>
            <p class="custom-hint">这些字段会同步到后端（用于自动填表），也可在扩展里按字段名匹配任意网申表单字段，覆盖标准画像未列举的信息。分类专属字段请在各标签页底部添加。</p>
            <div class="custom-add-row">
                <input type="text" id="custom-key-input" class="skill-add-input" placeholder="字段名，如：外语能力">
                <input type="text" id="custom-value-input" class="skill-add-input" placeholder="字段值，如：日语 N2">
                <button class="btn btn-primary btn-sm" data-action="add-custom">添加</button>
            </div>
            <div class="custom-list">${rows}</div>
        </div>`;
    }

    function addCustomField() {
        const keyEl = root.querySelector('#custom-key-input');
        const valEl = root.querySelector('#custom-value-input');
        if (!keyEl || !valEl) return;
        const key = keyEl.value.trim();
        const val = valEl.value.trim();
        if (!key) { API.toast('请填写字段名', 'warn'); return; }
        if (!state.profile.extra_fields) state.profile.extra_fields = {};
        if (Object.prototype.hasOwnProperty.call(state.profile.extra_fields, key)) {
            API.toast('该字段名已存在', 'warn'); return;
        }
        state.profile.extra_fields[key] = val;
        markDirty();
        renderTabPanel();
        API.toast('已添加自定义字段', 'info', 1200);
    }

    function deleteCustomField(key) {
        if (!state.profile.extra_fields) return;
        delete state.profile.extra_fields[key];
        markDirty();
        renderTabPanel();
        API.toast('已删除', 'success', 1200);
    }

    // --- JSON 备份 ---

    function renderJsonBackup() {
        const container = root.querySelector('#json-backup-container');
        if (!container) return;
        const json = JSON.stringify(state.profile, null, 2);
        container.innerHTML = `
        <div class="json-backup">
            <div class="json-backup-head">
                <span class="json-backup-title">JSON 备份</span>
                <div class="json-backup-actions">
                    <button class="btn btn-ghost btn-sm" id="btn-copy-json">复制 JSON</button>
                    <button class="btn btn-ghost btn-sm" id="btn-download-json">下载文件</button>
                </div>
            </div>
            <pre>${esc(json)}</pre>
        </div>`;

        const copyBtn = container.querySelector('#btn-copy-json');
        if (copyBtn) {
            copyBtn.onclick = async () => {
                try {
                    await navigator.clipboard.writeText(json);
                    API.toast('JSON 已复制到剪贴板', 'success');
                } catch (e) {
                    // Fallback
                    const ta = document.createElement('textarea');
                    ta.value = json;
                    document.body.appendChild(ta);
                    ta.select();
                    try {
                        document.execCommand('copy');
                        API.toast('JSON 已复制到剪贴板', 'success');
                    } catch (e2) {
                        API.toast('复制失败，请手动选择文本', 'error');
                    }
                    ta.remove();
                }
            };
        }

        const dlBtn = container.querySelector('#btn-download-json');
        if (dlBtn) {
            dlBtn.onclick = () => {
                const blob = new Blob([json], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'offercabin-profile-' + new Date().toISOString().slice(0, 10) + '.json';
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                API.toast('已开始下载', 'success');
            };
        }
    }

    // ============ 事件绑定 ============

    function bindEvents() {
        // Tab 切换
        const tabsEl = root.querySelector('#profile-tabs');
        if (tabsEl) {
            tabsEl.addEventListener('click', (e) => {
                const tab = e.target.closest('.tab');
                if (!tab) return;
                const key = tab.dataset.tab;
                if (key && key !== state.activeTab) {
                    state.activeTab = key;
                    updateTabsUI();
                    renderTabPanel();
                }
            });
        }

        // 保存按钮
        const saveBtn = root.querySelector('#btn-save');
        if (saveBtn) {
            saveBtn.addEventListener('click', saveProfile);
        }

        // 导入 PDF
        const importBtn = root.querySelector('#btn-import-pdf');
        const pdfInput = root.querySelector('#pdf-file-input');
        if (importBtn && pdfInput) {
            importBtn.addEventListener('click', () => pdfInput.click());
            pdfInput.addEventListener('change', () => {
                if (pdfInput.files && pdfInput.files[0]) {
                    uploadPdf(pdfInput.files[0]);
                    pdfInput.value = '';
                }
            });
        }
    }

    function updateTabsUI() {
        root.querySelectorAll('#profile-tabs .tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === state.activeTab);
        });
    }

    function bindPanelEvents() {
        const panel = root.querySelector('#tab-panels');
        if (!panel) return;

        // 表单字段变更（委托）
        panel.addEventListener('input', onFieldInput);
        panel.addEventListener('change', onFieldInput);

        // 添加/删除条目
        panel.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;
            const action = btn.dataset.action;
            if (action === 'add-entry') {
                addEntry(btn.dataset.section);
            } else if (action === 'delete-entry') {
                deleteEntry(btn.dataset.section, parseInt(btn.dataset.index, 10));
            } else if (action === 'delete-skill') {
                deleteSkill(parseInt(btn.dataset.index, 10));
            } else if (action === 'delete-tag') {
                deleteTag(btn.dataset.field, parseInt(btn.dataset.index, 10));
            } else if (action === 'add-custom') {
                addCustomField();
            } else if (action === 'delete-custom') {
                deleteCustomField(btn.dataset.key);
            } else if (action === 'add-section-custom') {
                addSectionCustomField(btn.dataset.section);
            } else if (action === 'delete-section-custom') {
                deleteSectionCustomField(btn.dataset.section, btn.dataset.key);
            } else if (action === 'add-entry-custom') {
                addEntryCustomField(btn.dataset.section, parseInt(btn.dataset.index, 10));
            } else if (action === 'delete-entry-custom') {
                deleteEntryCustomField(btn.dataset.section, parseInt(btn.dataset.index, 10), btn.dataset.key);
            }
        });

        // 自定义字段：回车快捷添加
        const customVal = panel.querySelector('#custom-value-input');
        if (customVal) {
            customVal.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); addCustomField(); }
            });
        }

        // 分类内自定义字段：任一输入框回车快速添加
        Object.keys(SECTION_CUSTOM_LABELS).forEach((sec) => {
            const secVal = panel.querySelector('#sec-custom-val-' + sec);
            if (secVal) {
                secVal.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { e.preventDefault(); addSectionCustomField(sec); }
                });
            }
            const secKey = panel.querySelector('#sec-custom-key-' + sec);
            if (secKey) {
                secKey.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { e.preventDefault(); addSectionCustomField(sec); }
                });
            }
        });

        // 条目级自定义字段：任一输入框回车快速添加
        ['education', 'experience', 'projects', 'certificates', 'languages', 'awards', 'essays', 'publications', 'patents'].forEach((sec) => {
            panel.querySelectorAll('[id^="ecf-key-' + sec + '-"]').forEach((el) => {
                const idx = el.id.split('-').pop();
                el.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { e.preventDefault(); addEntryCustomField(sec, parseInt(idx, 10)); }
                });
            });
            panel.querySelectorAll('[id^="ecf-val-' + sec + '-"]').forEach((el) => {
                const idx = el.id.split('-').pop();
                el.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { e.preventDefault(); addEntryCustomField(sec, parseInt(idx, 10)); }
                });
            });
        });

        // 技能添加
        const skillInput = panel.querySelector('#skill-name-input');
        const skillAddBtn = panel.querySelector('#skill-add-btn');
        if (skillInput) {
            skillInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addSkill();
                }
            });
        }
        if (skillAddBtn) {
            skillAddBtn.addEventListener('click', addSkill);
        }

        // 标签添加（职位/城市）
        panel.querySelectorAll('.tag-add-input').forEach(input => {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addTag(input.dataset.field, input.value.trim());
                    input.value = '';
                }
            });
        });
    }

    function onFieldInput(e) {
        const el = e.target;
        if (!el || !el.dataset || !el.dataset.field) return;
        // 排除标签添加输入框
        if (el.classList.contains('tag-add-input')) return;
        handleFieldChange(el);
    }

    function handleFieldChange(el) {
        const section = el.dataset.section;
        const field = el.dataset.field;
        const index = el.dataset.index;
        const type = el.dataset.type;
        let value = el.value;

        if (type === 'text-array') {
            value = achievementsToArray(value);
        } else if (type === 'csv-array') {
            value = techStackToArray(value);
        } else if (el.type === 'number') {
            value = value === '' ? '' : Number(value);
        }

        if (index !== undefined) {
            const idx = parseInt(index, 10);
            if (state.profile[section] && state.profile[section][idx]) {
                state.profile[section][idx][field] = value;
            }
        } else {
            if (state.profile[section]) {
                state.profile[section][field] = value;
            }
        }
        markDirty();
    }

    // ============ 条目操作 ============

    function addEntry(section) {
        const templates = {
            education: { school: '', degree: '', major: '', school_type: '', edu_form: '', courses: '', start_date: '', end_date: '', gpa: '', description: '', custom_fields: {} },
            experience: { company: '', position: '', start_date: '', end_date: '', description: '', achievements: [], custom_fields: {} },
            projects: { name: '', role: '', description: '', start_date: '', end_date: '', url: '', tech_stack: [], custom_fields: {} },
            certificates: { name: '', issuer: '', date: '', score: '', custom_fields: {} },
            languages: { name: '', proficiency: '', test_score: '', custom_fields: {} },
            awards: { name: '', level: '', issuer: '', date: '', description: '', custom_fields: {} },
            essays: { question: '', answer: '', tag: '', custom_fields: {} },
            publications: { title: '', venue: '', level: '', authors: '', role: '', date: '', doi: '', description: '', custom_fields: {} },
            patents: { name: '', patent_no: '', type: '', status: '', holder: '', inventors: '', date: '', description: '', custom_fields: {} },
        };
        if (!templates[section]) return;
        state.profile[section].push(templates[section]);
        markDirty();
        renderTabPanel();
        API.toast('已添加新条目', 'info', 1500);
    }

    function deleteEntry(section, index) {
        if (!state.profile[section] || !state.profile[section][index]) return;
        if (!confirm('确定删除此条目？')) return;
        state.profile[section].splice(index, 1);
        markDirty();
        renderTabPanel();
        API.toast('已删除', 'success', 1500);
    }

    // ============ 技能操作 ============

    function addSkill() {
        const nameEl = root.querySelector('#skill-name-input');
        const levelEl = root.querySelector('#skill-level-select');
        const catEl = root.querySelector('#skill-category-select');
        if (!nameEl) return;
        const name = nameEl.value.trim();
        if (!name) {
            API.toast('请输入技能名称', 'warn');
            return;
        }
        // 去重
        if (state.profile.skills.some(s => s.name === name)) {
            API.toast('该技能已存在', 'warn');
            return;
        }
        state.profile.skills.push({
            name: name,
            level: levelEl ? levelEl.value : '熟悉',
            category: catEl ? catEl.value : '',
        });
        markDirty();
        renderTabPanel();
        nameEl.value = '';
        nameEl.focus();
    }

    function deleteSkill(index) {
        if (!state.profile.skills[index]) return;
        state.profile.skills.splice(index, 1);
        markDirty();
        renderTabPanel();
    }

    // ============ 标签操作 ============

    function addTag(field, value) {
        if (!value) return;
        const arr = state.profile.job_intent[field];
        if (!Array.isArray(arr)) return;
        if (arr.includes(value)) {
            API.toast('已存在', 'warn');
            return;
        }
        arr.push(value);
        markDirty();
        renderTabPanel();
        // 重新聚焦输入框
        const inputId = field === 'target_positions' ? '#input-positions' : '#input-cities';
        const input = root.querySelector(inputId);
        if (input) input.focus();
    }

    function deleteTag(field, index) {
        const arr = state.profile.job_intent[field];
        if (!Array.isArray(arr) || !arr[index]) return;
        arr.splice(index, 1);
        markDirty();
        renderTabPanel();
    }

    // ============ 数据加载与保存 ============

    async function loadProfile() {
        state.loading = true;
        state.error = null;
        root.innerHTML = renderLoading();
        try {
            const [profile, completion] = await Promise.all([
                API.get('/profiles/'),
                API.get('/profiles/completion').catch(() => ({ percentage: 0, overall: 0, sections: {} })),
            ]);
            state.profile = normalizeProfile(profile);
            state.completion = completion || { percentage: 0, overall: 0, sections: {} };
            state.dirty = false;
            state.loading = false;
            renderAll();
        } catch (e) {
            state.loading = false;
            state.error = e.message || '加载失败';
            // 初始化空画像供编辑
            state.profile = emptyProfile();
            state.completion = { percentage: 0, overall: 0, sections: {} };
            state.dirty = false;
            root.innerHTML = renderShell();
            bindEvents();
            renderTabPanel();
            renderJsonBackup();
            updateSaveStatus();
            updateCompletion();
            API.toast('画像数据加载失败，已初始化空画像: ' + state.error, 'warn', 4000);
        }
    }

    async function loadCompletion() {
        try {
            const data = await API.get('/profiles/completion');
            state.completion = data || { percentage: 0, overall: 0, sections: {} };
            updateCompletion();
        } catch (e) {
            // 静默失败
        }
    }

    async function saveProfile() {
        if (!state.dirty || state.saving) return;
        state.saving = true;
        updateSaveStatus();
        try {
            // 清理 achievements 和 tech_stack 数组化
            const payload = JSON.parse(JSON.stringify(state.profile));
            payload.experience = (payload.experience || []).map(e => ({
                ...e,
                achievements: Array.isArray(e.achievements) ? e.achievements :
                    (typeof e.achievements === 'string' ? achievementsToArray(e.achievements) : []),
            }));
            payload.projects = (payload.projects || []).map(p => ({
                ...p,
                tech_stack: Array.isArray(p.tech_stack) ? p.tech_stack :
                    (typeof p.tech_stack === 'string' ? techStackToArray(p.tech_stack) : []),
            }));
            // 前端 ↔ 后端字段名对齐：basic → basic_info，certificates → certifications
            payload.basic_info = payload.basic;
            delete payload.basic;
            payload.certifications = payload.certificates;
            delete payload.certificates;

            await API.post('/profiles/', payload);
            state.dirty = false;
            API.toast('画像已保存', 'success');
            await loadCompletion();
        } catch (e) {
            API.toast('保存失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.saving = false;
            updateSaveStatus();
        }
    }

    // ============ PDF 导入 ============

    async function uploadPdf(file) {
        if (!file) return;
        API.toast('正在解析 PDF...', 'info', 3000);
        const fd = new FormData();
        fd.append('file', file);
        try {
            // 走统一 API 客户端：自动带 JWT 鉴权头 + 统一错误处理（否则 401：未登录或缺少访问令牌）
            const data = await API.postForm('/profiles/import-pdf', fd);
            const parsed = normalizeProfile((data && data.profile) || {});
            const filled = countFilled(parsed);
            mergeProfile(parsed);
            state.dirty = true;
            renderAll();
            updateSaveStatus();
            const srcMap = { llm: 'LLM', rules: '规则', empty: '空', error: '失败' };
            const src = (data && srcMap[data.source]) || '未知';
            if (filled === 0) {
                API.toast('PDF 解析完成但未提取到有效信息（' + src + '），请手动填写', 'warn', 5000);
            } else {
                API.toast(`PDF 解析完成（${src}），已填充约 ${filled} 项，请核对后保存`, 'success', 5000);
            }
        } catch (e) {
            API.toast('PDF 解析失败: ' + (e.message || '未知错误'), 'error', 6000);
        }
    }

    function mergeProfile(parsed) {
        const cur = state.profile;
        if (parsed.basic) {
            Object.keys(parsed.basic).forEach(k => {
                if (parsed.basic[k] !== '' && parsed.basic[k] != null) cur.basic[k] = parsed.basic[k];
            });
        }
        if (Array.isArray(parsed.education) && parsed.education.length) cur.education = parsed.education;
        if (Array.isArray(parsed.experience) && parsed.experience.length) cur.experience = parsed.experience;
        if (Array.isArray(parsed.projects) && parsed.projects.length) cur.projects = parsed.projects;
        if (Array.isArray(parsed.skills) && parsed.skills.length) cur.skills = parsed.skills;
        if (Array.isArray(parsed.certificates) && parsed.certificates.length) cur.certificates = parsed.certificates;
        if (Array.isArray(parsed.languages) && parsed.languages.length) cur.languages = parsed.languages;
        if (Array.isArray(parsed.awards) && parsed.awards.length) cur.awards = parsed.awards;
        if (Array.isArray(parsed.essays) && parsed.essays.length) cur.essays = parsed.essays;
        if (Array.isArray(parsed.publications) && parsed.publications.length) cur.publications = parsed.publications;
        if (Array.isArray(parsed.patents) && parsed.patents.length) cur.patents = parsed.patents;
        if (parsed.summary) {
            Object.keys(parsed.summary).forEach(k => {
                if (parsed.summary[k] !== '' && parsed.summary[k] != null) cur.summary[k] = parsed.summary[k];
            });
        }
        if (parsed.job_intent) {
            if (Array.isArray(parsed.job_intent.target_positions) && parsed.job_intent.target_positions.length)
                cur.job_intent.target_positions = parsed.job_intent.target_positions;
            if (Array.isArray(parsed.job_intent.target_cities) && parsed.job_intent.target_cities.length)
                cur.job_intent.target_cities = parsed.job_intent.target_cities;
            ['expected_salary', 'work_type', 'availability'].forEach(k => {
                if (parsed.job_intent[k]) cur.job_intent[k] = parsed.job_intent[k];
            });
        }
    }

    function countFilled(p) {
        let n = 0;
        if (p.basic) Object.values(p.basic).forEach(v => { if (v !== '' && v != null) n++; });
        n += (p.education || []).length;
        n += (p.experience || []).length;
        n += (p.projects || []).length;
        n += (p.skills || []).length;
        n += (p.certificates || []).length;
        n += (p.languages || []).length;
        n += (p.awards || []).length;
        n += (p.essays || []).length;
        n += (p.publications || []).length;
        n += (p.patents || []).length;
        return n;
    }

    // ============ 全量渲染 ============

    function renderAll() {
        if (!root) return;
        root.innerHTML = renderShell();
        bindEvents();
        renderTabPanel();
        renderJsonBackup();
        updateSaveStatus();
        // 延迟更新完成度以确保过渡动画
        requestAnimationFrame(() => updateCompletion());
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();

        // 脏状态离开警告
        beforeUnloadHandler = (e) => {
            if (state.dirty) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        global.addEventListener('beforeunload', beforeUnloadHandler);

        await loadProfile();
    }

    function cleanup() {
        if (beforeUnloadHandler) {
            global.removeEventListener('beforeunload', beforeUnloadHandler);
            beforeUnloadHandler = null;
        }
        root = null;
    }

    global.OfferCabinViews = global.OfferCabinViews || {};
    global.OfferCabinViews.profile = { mount, cleanup, title: '简历画像' };
})(window);
