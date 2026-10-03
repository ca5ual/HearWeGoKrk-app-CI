// Help screen (WCAG 2.2 3.2.6 Consistent Help): opened from the same header button on every screen.
import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { Card, IconText, T, type IconName } from "@/components/ui";
import { space } from "@/theme";

const SECTIONS: { icon: IconName; title: string; lines: string[] }[] = [
  {
    icon: "mic",
    title: "Jak mówić do asystenta",
    lines: [
      "Duży przycisk zajmuje prawie cały ekran zakładki Mów.",
      "Przytrzymaj go i mów. Puść, aby wysłać.",
      "Albo stuknij raz, powiedz, czego potrzebujesz, i stuknij jeszcze raz. Z czytnikiem ekranu: dwukrotne stuknięcie zaczyna, kolejne wysyła.",
    ],
  },
  {
    icon: "x",
    title: "Jak anulować nagrywanie",
    lines: [
      "Zsuń palec z przycisku, zanim go puścisz, albo stuknij „Anuluj” pod przyciskiem.",
      "Nic nie zostanie wysłane.",
    ],
  },
  {
    icon: "message-square-text",
    title: "Co możesz powiedzieć",
    lines: ["„Jak dojadę na Rynek?”", "„Kiedy następna czternastka?”", "„Wsiadłem”", "„Kup bilet”", "„Stop” — przerywa i anuluje"],
  },
  {
    icon: "rotate-ccw",
    title: "Gdy nie usłyszysz odpowiedzi",
    lines: ["Stuknij „Powtórz” na ekranie Mów.", "Pełny tekst rozmowy jest pod przyciskiem „Tekst rozmowy”."],
  },
  {
    icon: "shopping-cart",
    title: "Bilety",
    lines: [
      "Bilet kupisz tylko po wyraźnym „tak” albo po stuknięciu „Potwierdź”. Cisza nigdy nie oznacza zgody.",
      "Jeśli potrzebujesz chwili, stuknij „Potrzebuję więcej czasu”.",
    ],
  },
  {
    icon: "route",
    title: "Zakładki",
    lines: [
      "Mów — rozmowa z asystentem.",
      "Trasa — ostatnio wyszukana trasa i wyszukiwanie krok po kroku.",
      "Rozkłady — najbliższe odjazdy z przystanku.",
      "Aplikacja nie przełącza ekranów sama: wyniki czekają w zakładkach.",
    ],
  },
  {
    icon: "accessibility",
    title: "Ułatwienia dostępu",
    lines: [
      "Aplikacja działa z TalkBack i VoiceOver.",
      "Działa z powiększonym tekstem i w poziomie.",
      "Gdy w telefonie wyłączysz animacje, aplikacja też ich nie pokazuje.",
    ],
  },
];

export default function Help() {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      {SECTIONS.map((s) => (
        <Card key={s.title} style={styles.card}>
          <IconText variant="title" icon={s.icon} accessibilityRole="header">{s.title}</IconText>
          <View style={{ gap: space(1) }}>
            {s.lines.map((l) => <T key={l}>{l}</T>)}
          </View>
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(3), paddingBottom: space(12) },
  card: { gap: space(2) },
});
