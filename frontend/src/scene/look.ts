/** Seeded Central-Asian look so every citizen is visually unique. */

const SKIN = ["#F0D2B4", "#E8C39E", "#DDB18C", "#CE9E76", "#BC8A62", "#A87550", "#96633F"];
const EYES = ["#5A3A22", "#3E2415", "#2A1810", "#7B5B33", "#6B4A2A"];
const HAIR_DARK = ["#1A1412", "#2B1F1A", "#3B2A20", "#4E372A"];
const HAIR_GREY = ["#6E6259", "#8A8078", "#9A928B"];
const ATLAS = ["#C41E3A", "#1F6B4A", "#C9A227", "#1E4D8C", "#D45A00", "#6B1E6B"];
const CHAPAN = ["#1F4D2A", "#3D2B1F", "#5C1A1A", "#1A3A5C", "#4A3A1A"];
const DOPPI = ["#111111", "#F4F0E6", "#1F4D2A", "#5C1A1A"];

export interface Look {
  skin: string;
  eyes: string;
  hair: string;
  hairStyle: "short" | "buzz" | "side" | "long" | "braid" | "bun" | "grey";
  clothes: string;
  clothes2: string;
  shoes: string;
  doppi: string | null;
  beard: boolean;
  body: number;
  female: boolean;
}

export function lookFromSeed(
  seed: string,
  gender: string,
  age: number,
  profession: string | null,
  president = false,
): Look {
  const h = hash(seed);
  const female = gender === "female";
  const senior = age >= 55;
  const hairPool = senior ? HAIR_GREY : HAIR_DARK;
  const job = (profession ?? "").toLowerCase();

  let clothes = female ? pick(ATLAS, h, 11) : pick(CHAPAN, h, 11);
  let clothes2 = pick(ATLAS, h, 23);
  if (president) {
    clothes = "#1A2744";
    clothes2 = "#C9A227";
  } else if (job.includes("doctor") || job.includes("nurse")) {
    clothes = "#F4F4F0";
    clothes2 = "#C05050";
  } else if (job.includes("police")) {
    clothes = "#1E3A5F";
    clothes2 = "#C9A227";
  } else if (job.includes("teacher")) {
    clothes = "#2F5D73";
  } else if (job.includes("farmer")) {
    clothes = "#6B4A2A";
  } else if (job.includes("chef")) {
    clothes = "#EEEEEE";
  } else if (job.includes("builder") || job.includes("engineer")) {
    clothes = "#C45A12";
  }

  const maleHair: Look["hairStyle"][] = ["short", "buzz", "side"];
  const femaleHair: Look["hairStyle"][] = ["long", "braid", "bun"];

  return {
    skin: pick(SKIN, h, 3),
    eyes: pick(EYES, h, 7),
    hair: pick(hairPool, h, 13),
    hairStyle: senior && !female ? "grey" : pick(female ? femaleHair : maleHair, h, 17),
    clothes,
    clothes2,
    shoes: pick(["#1A1412", "#3B2A20", "#4A3020"], h, 19),
    doppi: female ? null : president ? "#C9A227" : pick(DOPPI, h, 29),
    beard: !female && age > 22 && (h % 5 !== 0),
    body: 0.92 + ((h >> 8) % 20) / 100,
    female,
  };
}

export const ACTIVITY_LINE: Record<string, string> = {
  commuting: "Ishga ketayapman",
  going_home: "Uyga qaytyapman",
  shopping: "Do'konga ketyapman",
  at_school: "Maktabdaman",
  working: "Ishlamoqdaman",
  leisure: "Parkda sayr",
  socialising: "Do'stlar bilan",
  eating: "Ovqatlanmoqdaman",
  at_hospital: "Shifokorga",
  seeking_job: "Ish qidirayapman",
  sleeping: "Uxlayapman",
  idle: "Ko'chada",
  reports: "Hisobot o'qiyapman",
  meetings: "Yig'ilishdaman",
  inspections: "Shaharni ko'ryapman",
  planning: "Reja tuzayapman",
  family: "Oila bilan",
  breakfast: "Nonushta",
  lunch: "Tushlik",
  office: "Idoradaman",
  city: "Shaharda",
};

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

function pick<T>(items: readonly T[], h: number, salt: number): T {
  return items[(h + salt * 997) % items.length];
}
