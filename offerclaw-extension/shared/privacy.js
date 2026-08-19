// OfferClaw 扩展 - 本地敏感字段识别与本地值管理
// 敏感数据（身份证/住址/银行卡/护照）仅存浏览器本地，后端永不接触
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_privacy) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_privacy = true;

  const SENS = OC.schema.SENSITIVE_KEYS;

  OC.privacy = {
    // 判断字段是否敏感（依据 label/name/id 文本）
    isSensitive(fieldText) {
      const t = (fieldText || "").toLowerCase();
      if (!t) return false;
      return SENS.some((k) => t.includes(k.toLowerCase()));
    },

    // 从本地存储读取对应敏感值
    async getLocalValue(fieldText) {
      const sens = (await OC.store.get("sensitive_local")) || {};
      const t = (fieldText || "").toLowerCase();
      if (/身份证|id_card|idcard|identity|身份号|身份证明/.test(t)) return sens.id_card || "";
      if (/护照|passport/.test(t)) return sens.passport || "";
      if (/住址|address|家庭住址|地址/.test(t)) return sens.home_address || "";
      if (/银行卡|bank|银行账号/.test(t)) return sens.bank_card || "";
      if (/紧急联系人|emergency_contact|紧急电话|emergency_phone/.test(t)) {
        // 表单可能要的是名字或电话，优先返回姓名，匹配不到名字时返回电话
        return sens.emergency_contact || sens.emergency_phone || "";
      }
      return "";
    },

    async getSensitive() {
      return (await OC.store.get("sensitive_local")) || {};
    },

    async setSensitive(map) {
      await OC.store.update("sensitive_local", map);
    }
  };
})();
