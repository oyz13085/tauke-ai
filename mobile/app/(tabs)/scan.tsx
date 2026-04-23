/**
 * Scan screen — photograph a supplier receipt and track processing status.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as ImagePicker from "expo-image-picker";
import { api, Invoice, SHOP_ID_KEY } from "../../services/api";

type Step = "idle" | "uploading" | "polling" | "done" | "failed" | "needs_review";

export default function ScanScreen() {
  const [shopId,  setShopId]  = useState<string | null>(null);
  const [step,    setStep]    = useState<Step>("idle");
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(SHOP_ID_KEY).then((id) => setShopId(id));
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const startPolling = useCallback((invoiceId: string) => {
    setStep("polling");
    pollRef.current = setInterval(async () => {
      try {
        const inv = await api.getInvoice(invoiceId);
        setInvoice(inv);
        if (inv.processing_status === "done") {
          stopPolling();
          setStep("done");
        } else if (inv.processing_status === "failed") {
          stopPolling();
          setStep("failed");
          setError("Proses OCR gagal. Cuba lagi dengan gambar yang lebih jelas.");
        } else if (inv.processing_status === "needs_review") {
          stopPolling();
          setStep("needs_review");
        }
      } catch (e: unknown) {
        stopPolling();
        setError((e as Error).message);
        setStep("failed");
      }
    }, 2000);
  }, []);

  const pickAndUpload = useCallback(async (source: "camera" | "library") => {
    if (!shopId) { Alert.alert("Setup diperlukan", "Sila set up kedai anda dahulu."); return; }

    const granted =
      source === "camera"
        ? (await ImagePicker.requestCameraPermissionsAsync()).granted
        : (await ImagePicker.requestMediaLibraryPermissionsAsync()).granted;

    if (!granted) {
      Alert.alert("Kebenaran diperlukan", "Benarkan akses kamera / galeri.");
      return;
    }

    const result =
      source === "camera"
        ? await ImagePicker.launchCameraAsync({ quality: 0.9, allowsEditing: false })
        : await ImagePicker.launchImageLibraryAsync({ quality: 0.9, mediaTypes: ["images"] });

    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const filename = asset.fileName ?? "receipt.jpg";
    const mimeType = asset.mimeType ?? "image/jpeg";

    setStep("uploading");
    setError(null);
    setInvoice(null);

    try {
      const inv = await api.uploadInvoice(shopId, asset.uri, filename, mimeType);
      setInvoice(inv);
      startPolling(inv.id);
    } catch (e: unknown) {
      setStep("failed");
      setError((e as Error).message);
    }
  }, [shopId, startPolling]);

  const reset = () => { stopPolling(); setStep("idle"); setInvoice(null); setError(null); };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        {/* Title */}
        <Text style={styles.title}>Scan Invois</Text>
        <Text style={styles.subtitle}>Ambil gambar invois pembekal anda</Text>

        {/* Status card */}
        {step !== "idle" && <StatusCard step={step} invoice={invoice} error={error} />}

        {/* Action buttons */}
        {step === "idle" && (
          <View style={styles.btnGroup}>
            <TouchableOpacity
              style={[styles.btn, styles.btnPrimary]}
              onPress={() => pickAndUpload("camera")}
            >
              <Text style={styles.btnPrimaryText}>📷  Buka Kamera</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.btn, styles.btnSecondary]}
              onPress={() => pickAndUpload("library")}
            >
              <Text style={styles.btnSecondaryText}>🖼️  Pilih dari Galeri</Text>
            </TouchableOpacity>
          </View>
        )}

        {(step === "done" || step === "failed" || step === "needs_review") && (
          <TouchableOpacity style={[styles.btn, styles.btnSecondary, { marginTop: 16 }]} onPress={reset}>
            <Text style={styles.btnSecondaryText}>Scan Lagi</Text>
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusCard({ step, invoice, error }: { step: Step; invoice: Invoice | null; error: string | null }) {
  const config: Record<Step, { emoji: string; title: string; desc: string; bg: string; border: string }> = {
    idle:         { emoji: "",   title: "",                          desc: "", bg: "", border: "" },
    uploading:    { emoji: "⬆️", title: "Menghantar gambar…",        desc: "Sila tunggu sebentar.",                         bg: "#eff6ff", border: "#bfdbfe" },
    polling:      { emoji: "🔍", title: "Memproses OCR…",             desc: "AI sedang membaca invois anda.",                bg: "#f0fdf4", border: "#bbf7d0" },
    done:         { emoji: "✅", title: "Berjaya!",                   desc: "Stok telah dikemaskini. Semak cadangan AI.",    bg: "#f0fdf4", border: "#86efac" },
    failed:       { emoji: "❌", title: "Proses gagal",               desc: error ?? "Ralat tidak diketahui.",               bg: "#fef2f2", border: "#fca5a5" },
    needs_review: { emoji: "👀", title: "Perlu semak semula",         desc: "Keyakinan OCR rendah. Semak data sebelum guna.", bg: "#fffbeb", border: "#fde68a" },
  };
  const c = config[step];
  if (!c.title) return null;

  return (
    <View style={[styles.statusCard, { backgroundColor: c.bg, borderColor: c.border }]}>
      <Text style={styles.statusEmoji}>{c.emoji}</Text>
      <Text style={styles.statusTitle}>{c.title}</Text>
      <Text style={styles.statusDesc}>{c.desc}</Text>
      {(step === "uploading" || step === "polling") && (
        <ActivityIndicator color={BRAND} style={{ marginTop: 12 }} />
      )}
      {invoice && step === "done" && (
        <View style={styles.invDetail}>
          {invoice.supplier_name && <Text style={styles.invLine}>Pembekal: {invoice.supplier_name}</Text>}
          {invoice.total_amount  && <Text style={styles.invLine}>Jumlah: MYR {invoice.total_amount.toFixed(2)}</Text>}
          {invoice.ocr_confidence && (
            <Text style={styles.invLine}>
              Keyakinan OCR: {Math.round(invoice.ocr_confidence * 100)}%
            </Text>
          )}
        </View>
      )}
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const BRAND = "#1e40af";

const styles = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: "#f8fafc" },
  container:   { flex: 1, padding: 24 },
  title:       { fontSize: 26, fontWeight: "800", color: BRAND, marginBottom: 6 },
  subtitle:    { fontSize: 14, color: "#64748b", marginBottom: 32 },
  statusCard: {
    borderWidth:  1.5,
    borderRadius: 16,
    padding:      20,
    alignItems:   "center",
    marginBottom: 24,
  },
  statusEmoji: { fontSize: 36, marginBottom: 10 },
  statusTitle: { fontSize: 18, fontWeight: "700", color: "#1e293b", textAlign: "center" },
  statusDesc:  { fontSize: 13, color: "#64748b",  textAlign: "center", marginTop: 6 },
  invDetail:   { marginTop: 14, width: "100%", gap: 4 },
  invLine:     { fontSize: 13, color: "#374151", textAlign: "center" },
  btnGroup:    { gap: 12, marginTop: 8 },
  btn:         { borderRadius: 14, paddingVertical: 16, alignItems: "center" },
  btnPrimary:  { backgroundColor: BRAND },
  btnSecondary:{ backgroundColor: "#ffffff", borderWidth: 1.5, borderColor: BRAND },
  btnPrimaryText:   { color: "#ffffff", fontSize: 16, fontWeight: "700" },
  btnSecondaryText: { color: BRAND,     fontSize: 16, fontWeight: "600" },
});
