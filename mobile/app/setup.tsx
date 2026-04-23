/**
 * First-run setup — create a shop and store the shop ID locally.
 */
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import { api, SHOP_ID_KEY } from "../services/api";

export default function SetupScreen() {
  const router = useRouter();
  const [ownerName,  setOwnerName]  = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [shopName,   setShopName]   = useState("");
  const [shopType,   setShopType]   = useState("mamak");
  const [loading,    setLoading]    = useState(false);

  const submit = async () => {
    if (!ownerName.trim() || !ownerEmail.trim() || !shopName.trim()) {
      Alert.alert("Isi semua maklumat", "Nama, email, dan nama kedai diperlukan.");
      return;
    }
    setLoading(true);
    try {
      const shop = await api.createShop({
        owner_email: ownerEmail.trim(),
        owner_name:  ownerName.trim(),
        shop_name:   shopName.trim(),
        shop_type:   shopType,
      });
      await AsyncStorage.setItem(SHOP_ID_KEY, shop.id);
      router.replace("/(tabs)");
    } catch (e: unknown) {
      Alert.alert("Ralat", (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView contentContainerStyle={styles.scroll}>
          <Text style={styles.logo}>🍛</Text>
          <Text style={styles.title}>Selamat Datang ke Tauke.AI</Text>
          <Text style={styles.subtitle}>
            Sistem AI untuk bantu peniaga F&B urus stok dan harga lebih bijak.
          </Text>

          <View style={styles.form}>
            <Field label="Nama Anda" value={ownerName} onChangeText={setOwnerName} placeholder="Cth: Ahmad bin Ali" />
            <Field label="Email" value={ownerEmail} onChangeText={setOwnerEmail} placeholder="ahmad@email.com" keyboardType="email-address" />
            <Field label="Nama Kedai" value={shopName} onChangeText={setShopName} placeholder="Cth: Warung Pak Lah" />

            <Text style={styles.label}>Jenis Kedai</Text>
            <View style={styles.typeRow}>
              {["mamak", "kopitiam", "hawker", "cafe"].map((t) => (
                <TouchableOpacity
                  key={t}
                  style={[styles.typeBtn, shopType === t && styles.typeBtnActive]}
                  onPress={() => setShopType(t)}
                >
                  <Text style={[styles.typeText, shopType === t && styles.typeTextActive]}>
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity
              style={[styles.submitBtn, loading && { opacity: 0.7 }]}
              onPress={submit}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.submitText}>Mulakan Sekarang →</Text>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
  keyboardType,
}: {
  label: string;
  value: string;
  onChangeText: (t: string) => void;
  placeholder?: string;
  keyboardType?: "default" | "email-address";
}) {
  return (
    <View style={{ marginBottom: 16 }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#94a3b8"
        keyboardType={keyboardType ?? "default"}
        autoCapitalize="none"
      />
    </View>
  );
}

const BRAND = "#1e40af";

const styles = StyleSheet.create({
  safe:     { flex: 1, backgroundColor: "#f8fafc" },
  scroll:   { padding: 24, paddingBottom: 40 },
  logo:     { fontSize: 56, textAlign: "center", marginTop: 20, marginBottom: 12 },
  title:    { fontSize: 26, fontWeight: "800", color: BRAND, textAlign: "center" },
  subtitle: { fontSize: 14, color: "#64748b", textAlign: "center", marginTop: 8, marginBottom: 32 },
  form:     { gap: 0 },
  label:    { fontSize: 13, fontWeight: "600", color: "#374151", marginBottom: 6 },
  input: {
    backgroundColor: "#ffffff",
    borderWidth: 1.5,
    borderColor: "#e2e8f0",
    borderRadius: 12,
    padding: 14,
    fontSize: 15,
    color: "#1e293b",
  },
  typeRow:        { flexDirection: "row", gap: 8, marginBottom: 24, flexWrap: "wrap" },
  typeBtn:        { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: "#e2e8f0" },
  typeBtnActive:  { backgroundColor: BRAND },
  typeText:       { fontSize: 13, color: "#64748b", fontWeight: "600" },
  typeTextActive: { color: "#ffffff" },
  submitBtn: {
    backgroundColor: BRAND,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: "center",
    marginTop: 8,
  },
  submitText: { color: "#ffffff", fontSize: 16, fontWeight: "700" },
});
