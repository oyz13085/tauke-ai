/**
 * Dashboard screen — live inventory overview + top active recommendations.
 */
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import {
  api,
  confidenceColor,
  decisionEmoji,
  InventoryItem,
  parseGlmExplanation,
  Recommendation,
  SHOP_ID_KEY,
} from "../../services/api";

export default function DashboardScreen() {
  const router = useRouter();
  const [shopId,   setShopId]   = useState<string | null>(null);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [recs,      setRecs]      = useState<Recommendation[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(SHOP_ID_KEY).then((id) => {
      if (id) setShopId(id);
      else router.replace("/setup");
    });
  }, []);

  const load = useCallback(async () => {
    if (!shopId) return;
    try {
      const [inv, recList] = await Promise.all([
        api.listInventory(shopId),
        api.listRecommendations(shopId),
      ]);
      setInventory(inv);
      setRecs(recList.slice(0, 3));
      setError(null);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }, [shopId]);

  useEffect(() => { if (shopId) { setLoading(true); load().finally(() => setLoading(false)); } }, [shopId]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  // Inventory items expiring within 3 days
  const expiringItems = inventory.filter((i) => {
    if (!i.expiry_date) return false;
    const daysLeft = Math.ceil(
      (new Date(i.expiry_date).getTime() - Date.now()) / 86_400_000
    );
    return daysLeft <= 3 && daysLeft >= 0;
  });

  if (loading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator size="large" color={BRAND} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Tauke.AI</Text>
          <Text style={styles.subtitle}>Dashboard Stok & Cadangan</Text>
        </View>

        {error && <Text style={styles.error}>{error}</Text>}

        {/* Expiry warning banner */}
        {expiringItems.length > 0 && (
          <View style={styles.warningBanner}>
            <Text style={styles.warningText}>
              ⏰ {expiringItems.length} item akan tamat tempoh dalam 3 hari!
            </Text>
          </View>
        )}

        {/* Stats row */}
        <View style={styles.statsRow}>
          <StatCard label="Jenis Produk" value={inventory.length.toString()} />
          <StatCard label="Cadangan Aktif" value={recs.length.toString()} color={recs.length > 0 ? "#f59e0b" : undefined} />
          <StatCard label="Hampir Luput" value={expiringItems.length.toString()} color={expiringItems.length > 0 ? "#ef4444" : undefined} />
        </View>

        {/* Active recommendations preview */}
        {recs.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Cadangan Terkini</Text>
            {recs.map((rec) => (
              <RecMiniCard key={rec.id} rec={rec} />
            ))}
            <TouchableOpacity
              style={styles.seeAllBtn}
              onPress={() => router.push("/(tabs)/recommendations")}
            >
              <Text style={styles.seeAllText}>Lihat semua cadangan →</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Inventory list */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Stok Semasa</Text>
          {inventory.length === 0 ? (
            <Text style={styles.empty}>Tiada stok. Scan invois untuk mula.</Text>
          ) : (
            inventory.map((item) => <InventoryRow key={item.id} item={item} />)
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.statCard}>
      <Text style={[styles.statValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function RecMiniCard({ rec }: { rec: Recommendation }) {
  const glm = parseGlmExplanation(rec.glm_explanation);
  const headline = glm?.headline ?? rec.recommended_action;
  const confColor = confidenceColor(rec.confidence_score);
  return (
    <View style={styles.recMini}>
      <Text style={styles.recEmoji}>{decisionEmoji(rec.recommendation_type)}</Text>
      <View style={{ flex: 1 }}>
        <Text style={styles.recHeadline} numberOfLines={2}>{headline}</Text>
        <Text style={[styles.recConf, { color: confColor }]}>
          Keyakinan: {Math.round(rec.confidence_score * 100)}%
        </Text>
      </View>
    </View>
  );
}

function InventoryRow({ item }: { item: InventoryItem }) {
  const expiring = item.expiry_date
    ? Math.ceil((new Date(item.expiry_date).getTime() - Date.now()) / 86_400_000)
    : null;
  const isLow = item.current_qty < 5;

  return (
    <View style={styles.invRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.invName}>{item.product_id.slice(0, 8)}…</Text>
        <Text style={styles.invUnit}>{item.current_qty} {item.unit}</Text>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        {isLow && <Text style={{ color: "#ef4444", fontSize: 11 }}>Stok rendah</Text>}
        {expiring !== null && expiring <= 3 && (
          <Text style={{ color: "#f59e0b", fontSize: 11 }}>Luput dalam {expiring}h</Text>
        )}
      </View>
    </View>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const BRAND = "#1e40af";

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: "#f8fafc" },
  center:  { flex: 1, justifyContent: "center", alignItems: "center" },
  scroll:  { padding: 16, paddingBottom: 32 },
  header:  { marginBottom: 20 },
  title:   { fontSize: 28, fontWeight: "800", color: BRAND },
  subtitle:{ fontSize: 14, color: "#64748b", marginTop: 2 },
  error:   { color: "#ef4444", marginBottom: 12, fontSize: 13 },
  warningBanner: {
    backgroundColor: "#fef3c7",
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
    borderLeftWidth: 4,
    borderLeftColor: "#f59e0b",
  },
  warningText: { color: "#92400e", fontWeight: "600", fontSize: 13 },
  statsRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 24,
  },
  statCard: {
    flex: 1,
    backgroundColor: "#ffffff",
    borderRadius: 14,
    padding: 14,
    alignItems: "center",
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 2,
  },
  statValue: { fontSize: 24, fontWeight: "800", color: "#1e293b" },
  statLabel: { fontSize: 11, color: "#64748b", marginTop: 4, textAlign: "center" },
  section:  { marginBottom: 24 },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: "#1e293b", marginBottom: 10 },
  empty:    { color: "#94a3b8", fontSize: 14, textAlign: "center", paddingVertical: 20 },
  recMini: {
    flexDirection: "row",
    backgroundColor: "#ffffff",
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
    alignItems: "flex-start",
    gap: 10,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 2,
  },
  recEmoji:    { fontSize: 22 },
  recHeadline: { fontSize: 13, fontWeight: "600", color: "#1e293b", lineHeight: 18 },
  recConf:     { fontSize: 11, marginTop: 2 },
  seeAllBtn:   { marginTop: 6, alignItems: "center" },
  seeAllText:  { color: BRAND, fontSize: 13, fontWeight: "600" },
  invRow: {
    flexDirection: "row",
    backgroundColor: "#ffffff",
    borderRadius: 12,
    padding: 12,
    marginBottom: 6,
    alignItems: "center",
    shadowColor: "#000",
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  invName: { fontSize: 13, fontWeight: "600", color: "#1e293b" },
  invUnit: { fontSize: 12, color: "#64748b", marginTop: 2 },
});
