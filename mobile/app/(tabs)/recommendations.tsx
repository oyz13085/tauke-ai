/**
 * Recommendations screen — full list with reasoning trace + Manglish explanation.
 */
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  api,
  confidenceColor,
  decisionEmoji,
  parseGlmExplanation,
  Recommendation,
  RecStatus,
  SHOP_ID_KEY,
} from "../../services/api";

export default function RecommendationsScreen() {
  const [shopId,     setShopId]     = useState<string | null>(null);
  const [recs,       setRecs]       = useState<Recommendation[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tab,        setTab]        = useState<RecStatus>("active");
  const [expanded,   setExpanded]   = useState<string | null>(null);

  useEffect(() => { AsyncStorage.getItem(SHOP_ID_KEY).then(setShopId); }, []);

  const load = useCallback(async () => {
    if (!shopId) return;
    const list = await api.listRecommendations(shopId, tab);
    setRecs(list);
  }, [shopId, tab]);

  useEffect(() => {
    if (shopId) { setLoading(true); load().finally(() => setLoading(false)); }
  }, [shopId, tab]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const handleFeedback = async (recId: string, rating: number) => {
    await api.submitFeedback(recId, rating);
    await load();
  };

  const handleDismiss = async (recId: string) => {
    await api.dismissRecommendation(recId);
    await load();
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator size="large" color={BRAND} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>💡 Cadangan AI</Text>
        {/* Tab bar */}
        <View style={styles.tabs}>
          {(["active", "acted_on", "dismissed"] as RecStatus[]).map((s) => (
            <TouchableOpacity
              key={s}
              style={[styles.tabBtn, tab === s && styles.tabBtnActive]}
              onPress={() => setTab(s)}
            >
              <Text style={[styles.tabText, tab === s && styles.tabTextActive]}>
                {s === "active" ? "Aktif" : s === "acted_on" ? "Dilaksana" : "Ditolak"}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <FlatList
        data={recs}
        keyExtractor={(r) => r.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {tab === "active" ? "Tiada cadangan aktif buat masa ini." : "Tiada rekod."}
          </Text>
        }
        renderItem={({ item }) => (
          <RecCard
            rec={item}
            expanded={expanded === item.id}
            onToggle={() => setExpanded((p) => (p === item.id ? null : item.id))}
            onFeedback={handleFeedback}
            onDismiss={handleDismiss}
          />
        )}
      />
    </SafeAreaView>
  );
}

// ── RecCard ────────────────────────────────────────────────────────────────

function RecCard({
  rec,
  expanded,
  onToggle,
  onFeedback,
  onDismiss,
}: {
  rec: Recommendation;
  expanded: boolean;
  onToggle: () => void;
  onFeedback: (id: string, r: number) => void;
  onDismiss: (id: string) => void;
}) {
  const glm = parseGlmExplanation(rec.glm_explanation);
  const confColor = confidenceColor(rec.confidence_score);
  const emoji = decisionEmoji(rec.recommendation_type);

  return (
    <View style={styles.card}>
      {/* Card header — tappable to expand */}
      <TouchableOpacity onPress={onToggle} activeOpacity={0.8}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardEmoji}>{emoji}</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardHeadline} numberOfLines={expanded ? undefined : 2}>
              {glm?.headline ?? rec.recommended_action}
            </Text>
            <View style={styles.metaRow}>
              <Text style={[styles.confBadge, { backgroundColor: confColor + "22", color: confColor }]}>
                {Math.round(rec.confidence_score * 100)}% yakin
              </Text>
              {(rec.risk_of_inaction ?? 0) > 0 && (
                <Text style={styles.riskBadge}>
                  Risiko MYR {rec.risk_of_inaction!.toFixed(2)}
                </Text>
              )}
            </View>
          </View>
          <Text style={styles.chevron}>{expanded ? "▲" : "▼"}</Text>
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.expandedBody}>
          {/* GLM explanation sections */}
          {glm && (
            <>
              <InfoBlock label="Kenapa?" text={glm.explanation} />
              <InfoBlock label="Impak Wang" text={glm.money_impact} />
              <InfoBlock label="Keyakinan" text={glm.confidence_statement} />
              <InfoBlock label="Langkah Seterusnya" text={glm.next_step} accent />
            </>
          )}

          {/* Reasoning trace summary */}
          <View style={styles.traceBox}>
            <Text style={styles.traceTitle}>📐 Trace Matematik</Text>
            <TraceRow label="Permintaan harian (asas)"   value={rec.reasoning_trace.base_demand_daily.toFixed(2)} />
            <TraceRow label="Permintaan dilaraskan"      value={rec.reasoning_trace.adjusted_demand_daily.toFixed(2)} />
            <TraceRow label="Stok boleh pakai"           value={rec.reasoning_trace.usable_stock.toFixed(2)} />
            <TraceRow label="Safety stock"               value={rec.reasoning_trace.safety_stock.toFixed(2)} />
            <TraceRow label="Cadangan order"             value={rec.reasoning_trace.target_order_qty.toFixed(2)} />
            <TraceRow
              label="Pengganda"
              value={`🌧${rec.reasoning_trace.multipliers_applied.weather}× 📅${rec.reasoning_trace.multipliers_applied.event}× 📆${rec.reasoning_trace.multipliers_applied.dow}×`}
            />
            {rec.reasoning_trace.context_signals_active.length > 0 && (
              <TraceRow label="Signal aktif" value={rec.reasoning_trace.context_signals_active.join(", ")} />
            )}
          </View>

          {/* Feedback stars (only for active recs) */}
          {rec.status === "active" && (
            <View style={styles.feedbackRow}>
              <Text style={styles.feedbackLabel}>Berguna?</Text>
              {[1, 2, 3, 4, 5].map((n) => (
                <TouchableOpacity key={n} onPress={() => onFeedback(rec.id, n)}>
                  <Text style={{ fontSize: 22 }}>{rec.feedback_rating && rec.feedback_rating >= n ? "⭐" : "☆"}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity style={styles.dismissBtn} onPress={() => onDismiss(rec.id)}>
                <Text style={styles.dismissText}>Tolak</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

function InfoBlock({ label, text, accent }: { label: string; text: string; accent?: boolean }) {
  return (
    <View style={[styles.infoBlock, accent && styles.infoBlockAccent]}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoText}>{text}</Text>
    </View>
  );
}

function TraceRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.traceRow}>
      <Text style={styles.traceLabel}>{label}</Text>
      <Text style={styles.traceValue}>{value}</Text>
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const BRAND = "#1e40af";

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: "#f8fafc" },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  header: { padding: 16, paddingBottom: 0 },
  title:  { fontSize: 24, fontWeight: "800", color: BRAND, marginBottom: 12 },
  tabs:   { flexDirection: "row", gap: 8, marginBottom: 4 },
  tabBtn: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 20, backgroundColor: "#e2e8f0",
  },
  tabBtnActive: { backgroundColor: BRAND },
  tabText:       { fontSize: 13, color: "#64748b", fontWeight: "600" },
  tabTextActive: { color: "#ffffff" },
  list:   { padding: 16, gap: 12, paddingBottom: 32 },
  empty:  { textAlign: "center", color: "#94a3b8", fontSize: 14, paddingVertical: 40 },

  // Card
  card: {
    backgroundColor: "#ffffff",
    borderRadius: 16,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    padding: 14,
    gap: 10,
  },
  cardEmoji:    { fontSize: 26, marginTop: 2 },
  cardHeadline: { fontSize: 14, fontWeight: "700", color: "#1e293b", lineHeight: 20 },
  metaRow:      { flexDirection: "row", gap: 6, marginTop: 6, flexWrap: "wrap" },
  confBadge: {
    fontSize: 11, fontWeight: "700", paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: 10,
  },
  riskBadge: {
    fontSize: 11, color: "#b91c1c", backgroundColor: "#fee2e2",
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10, fontWeight: "600",
  },
  chevron: { color: "#94a3b8", fontSize: 12, marginTop: 4 },

  // Expanded
  expandedBody: { paddingHorizontal: 14, paddingBottom: 14, gap: 8 },
  infoBlock: {
    backgroundColor: "#f8fafc",
    borderRadius: 10,
    padding: 10,
  },
  infoBlockAccent: { backgroundColor: "#eff6ff", borderLeftWidth: 3, borderLeftColor: BRAND },
  infoLabel: { fontSize: 11, fontWeight: "700", color: "#64748b", marginBottom: 4, textTransform: "uppercase" },
  infoText:  { fontSize: 13, color: "#1e293b", lineHeight: 18 },

  // Trace
  traceBox: {
    backgroundColor: "#f1f5f9",
    borderRadius: 10,
    padding: 10,
    gap: 4,
  },
  traceTitle: { fontSize: 12, fontWeight: "700", color: "#475569", marginBottom: 6 },
  traceRow:   { flexDirection: "row", justifyContent: "space-between" },
  traceLabel: { fontSize: 12, color: "#64748b", flex: 1 },
  traceValue: { fontSize: 12, fontWeight: "600", color: "#1e293b" },

  // Feedback
  feedbackRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingTop: 6,
  },
  feedbackLabel: { fontSize: 12, color: "#64748b", marginRight: 4 },
  dismissBtn: {
    marginLeft: "auto",
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 8,
    backgroundColor: "#f1f5f9",
  },
  dismissText: { fontSize: 12, color: "#64748b", fontWeight: "600" },
});
