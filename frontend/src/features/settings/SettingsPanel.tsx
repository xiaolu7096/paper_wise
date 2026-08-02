import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { getSettingsStatus, updateSettings, type SettingsStatus } from "../../api/client";

interface ModelForm {
  enabled: boolean;
  baseUrl: string;
  model: string;
  apiKey: string;
}

const emptyModel: ModelForm = { enabled: false, baseUrl: "", model: "", apiKey: "" };

export function SettingsPanel({ onClose, onStatusChange }: { onClose: () => void; onStatusChange?: (status: SettingsStatus) => void }) {
  const [text, setText] = useState<ModelForm>(emptyModel);
  const [vision, setVision] = useState<ModelForm>(emptyModel);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void getSettingsStatus().then((status) => {
      setText({
        enabled: status.text_model.configured,
        baseUrl: status.text_model.base_url ?? "",
        model: status.text_model.model ?? "",
        apiKey: "",
      });
      setVision({
        enabled: status.vision_model.configured,
        baseUrl: status.vision_model.base_url ?? "",
        model: status.vision_model.model ?? "",
        apiKey: "",
      });
    }).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "设置读取失败"));
  }, []);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const valid = (value: ModelForm) =>
    !value.enabled || Boolean(value.baseUrl.trim() && value.model.trim() && value.apiKey.trim());

  const save = async () => {
    if (!valid(text) || !valid(vision)) {
      setMessage("启用的模型必须填写地址、模型名和密钥");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const status = await updateSettings({
        text_model: text.enabled ? {
          base_url: text.baseUrl.trim(), model: text.model.trim(), api_key: text.apiKey.trim(),
        } : null,
        vision_model: vision.enabled ? {
          base_url: vision.baseUrl.trim(), model: vision.model.trim(), api_key: vision.apiKey.trim(),
        } : null,
      });
      onStatusChange?.(status);
      setMessage("设置已保存");
      setText((value) => ({ ...value, apiKey: "" }));
      setVision((value) => ({ ...value, apiKey: "" }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "设置保存失败");
    } finally {
      setSaving(false);
    }
  };

  const modelSection = (
    title: string,
    value: ModelForm,
    setValue: (value: ModelForm) => void,
  ) => (
    <fieldset className="model-settings">
      <legend>{title}</legend>
      <label className="toggle-row">
        <input type="checkbox" checked={value.enabled} onChange={(event) => setValue({ ...value, enabled: event.target.checked })} />
        启用
      </label>
      <label>Base URL<input value={value.baseUrl} disabled={!value.enabled} onChange={(event) => setValue({ ...value, baseUrl: event.target.value })} /></label>
      <label>模型名<input value={value.model} disabled={!value.enabled} onChange={(event) => setValue({ ...value, model: event.target.value })} /></label>
      <label>API Key<input type="password" value={value.apiKey} disabled={!value.enabled} placeholder={value.enabled ? "保存时必须重新输入" : ""} onChange={(event) => setValue({ ...value, apiKey: event.target.value })} /></label>
    </fieldset>
  );

  return (
    <div className="settings-overlay" role="dialog" aria-modal="true" aria-label="模型设置">
      <div className="settings-panel">
        <header><h2>模型设置</h2><button type="button" className="icon-button ghost" aria-label="关闭设置" title="关闭设置" onClick={onClose}><X size={18} /></button></header>
        {modelSection("文本模型", text, setText)}
        {modelSection("视觉模型", vision, setVision)}
        {message && <div role="status" className="settings-message">{message}</div>}
        <button type="button" className="save-settings" disabled={saving} onClick={() => void save()}>{saving ? "保存中" : "保存设置"}</button>
      </div>
    </div>
  );
}
