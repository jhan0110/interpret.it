export type FeatureStatus = "available" | "coming-soon";

export interface Feature {
  id: string;
  title: string;
  description: string;
  href: (learnerId: string) => string | null;
  status: FeatureStatus;
  statusKey: "training" | "vocab" | null;
}

export const FEATURES: Feature[] = [
  {
    id: "training",
    title: "Interpretation Training",
    description:
      "Live segment interpretation with prosody and semantic feedback.",
    href: (id) => `/learner/${id}/train`,
    status: "available",
    statusKey: "training",
  },
  {
    id: "vocab",
    title: "Vocabulary Deck",
    description: "Spaced-repetition flashcard review.",
    href: (id) => `/vocab/${id}`,
    status: "available",
    statusKey: "vocab",
  },
  {
    id: "memorization",
    title: "Memorization Practice",
    description:
      "Listen to a segment, then recall the key points from memory.",
    href: (id) => `/learner/${id}/memorize`,
    status: "available",
    statusKey: null,
  },
];
