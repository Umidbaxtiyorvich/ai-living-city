/**
 * Uzbek names for the identifiers the API sends.
 *
 * The backend deliberately streams enum values ("power_plant", "accountant")
 * because they are stable keys for the API and the database. Everything the
 * player reads is translated here, at the edge, so no screen shows an
 * identifier.
 */

export const BUILDING_LABELS: Record<string, string> = {
  house: "uy",
  townhouse: "ikki qavatli uy",
  apartment: "ko'p qavatli uy",
  city_hall: "hokimiyat binosi",
  presidential_palace: "prezident saroyi",
  courthouse: "sud binosi",
  police_station: "politsiya bo'limi",
  fire_station: "o't o'chirish bo'limi",
  kindergarten: "bog'cha",
  school: "maktab",
  university: "universitet",
  clinic: "klinika",
  hospital: "shifoxona",
  pharmacy: "dorixona",
  shop: "do'kon",
  market: "bozor",
  cafe: "kafe",
  restaurant: "restoran",
  office: "ofis",
  farm: "ferma",
  factory: "zavod",
  warehouse: "ombor",
  power_plant: "elektr stansiyasi",
  park: "park",
  zoo: "zoopark",
  cinema: "kinoteatr",
  sport_center: "sport majmuasi",
  bus_stop: "avtobus bekati",
  train_station: "temir yo'l vokzali",
};

export const PROFESSION_LABELS: Record<string, string> = {
  farmer: "fermer",
  doctor: "shifokor",
  nurse: "hamshira",
  teacher: "o'qituvchi",
  engineer: "muhandis",
  developer: "dasturchi",
  builder: "quruvchi",
  architect: "arxitektor",
  police: "politsiyachi",
  firefighter: "o't o'chiruvchi",
  driver: "haydovchi",
  shopkeeper: "sotuvchi",
  chef: "oshpaz",
  cleaner: "farrosh",
  factory_worker: "zavod ishchisi",
  scientist: "ilmiy xodim",
  accountant: "buxgalter",
  manager: "menejer",
  lawyer: "advokat",
  electrician: "elektrik",
  plumber: "santexnik",
  mechanic: "mexanik",
  security: "qorovul",
  gardener: "bog'bon",
  veterinarian: "veterinar",
};

export const BUILDING_STATUS_LABELS: Record<string, string> = {
  planned: "rejalashtirilgan",
  under_construction: "qurilmoqda",
  open: "ishlayapti",
  closed: "yopilgan",
  demolished: "buzilgan",
};

export function buildingLabel(type: string): string {
  return BUILDING_LABELS[type] ?? type;
}

export function professionLabel(profession: string | null): string {
  if (!profession) return "ishsiz";
  return PROFESSION_LABELS[profession] ?? profession;
}

export function buildingStatusLabel(status: string): string {
  return BUILDING_STATUS_LABELS[status] ?? status;
}
