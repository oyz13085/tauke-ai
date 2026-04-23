import { Tabs } from "expo-router";
import { StyleSheet, Text } from "react-native";

const BRAND = "#1e40af";   // Tauke.AI navy blue
const GRAY  = "#9ca3af";

function TabIcon({ emoji, label, focused }: { emoji: string; label: string; focused: boolean }) {
  return (
    <Text style={{ fontSize: focused ? 22 : 20, marginBottom: -4 }}>{emoji}</Text>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor:   BRAND,
        tabBarInactiveTintColor: GRAY,
        tabBarStyle:             styles.bar,
        tabBarLabelStyle:        styles.label,
        headerShown:             false,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Dashboard",
          tabBarIcon: ({ focused }) => <TabIcon emoji="📊" label="Dashboard" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="scan"
        options={{
          title: "Scan",
          tabBarIcon: ({ focused }) => <TabIcon emoji="📷" label="Scan" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="recommendations"
        options={{
          title: "AI Cadangan",
          tabBarIcon: ({ focused }) => <TabIcon emoji="💡" label="AI Cadangan" focused={focused} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: "#ffffff",
    borderTopWidth:  1,
    borderTopColor:  "#e5e7eb",
    height:          64,
    paddingBottom:   8,
  },
  label: {
    fontSize:    11,
    fontWeight:  "600",
  },
});
