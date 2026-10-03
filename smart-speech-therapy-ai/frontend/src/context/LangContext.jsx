import { createContext, useContext, useEffect, useMemo, useState } from "react";

const STRINGS = {
  en: {
    appName: "Smart Speech Therapy AI",
    nav_dashboard: "Dashboard",
    nav_disorders: "Disorders",
    nav_exercises: "Exercises",
    nav_games: "Games",
    nav_assessment: "Assessment",
    nav_assistant: "AI Assistant",
    nav_plans: "Therapy Plans",
    nav_specialist: "Specialist Workspace",
    nav_admin: "Admin",
    nav_logout: "Log out",
    login_title: "Welcome back",
    login_subtitle: "Log in to continue your practice.",
    login_email: "Email",
    login_password: "Password",
    login_submit: "Log in",
    login_no_account: "Don't have an account?",
    login_register_link: "Create one",
    register_title: "Create your account",
    register_name: "Full name",
    register_language: "Preferred language",
    register_submit: "Create account",
    register_has_account: "Already have an account?",
    register_login_link: "Log in",
    dashboard_welcome: "Welcome back",
    dashboard_subtitle: "Here's a snapshot of your practice.",
    common_loading: "Loading…",
    common_error: "Something went wrong",
    common_save: "Save",
    common_cancel: "Cancel",
    common_submit: "Submit",
    common_back: "Back",
  },
  ar: {
    appName: "منصة الذكاء الاصطناعي لعلاج النطق",
    nav_dashboard: "الرئيسية",
    nav_disorders: "الاضطرابات",
    nav_exercises: "التمارين",
    nav_games: "الألعاب",
    nav_assessment: "التقييم",
    nav_assistant: "المساعد الذكي",
    nav_plans: "خطط العلاج",
    nav_specialist: "مساحة المتخصص",
    nav_admin: "لوحة الإدارة",
    nav_logout: "تسجيل الخروج",
    login_title: "أهلاً بعودتك",
    login_subtitle: "سجّل الدخول لمتابعة تدريباتك.",
    login_email: "البريد الإلكتروني",
    login_password: "كلمة المرور",
    login_submit: "تسجيل الدخول",
    login_no_account: "ليس لديك حساب؟",
    login_register_link: "أنشئ حساباً",
    register_title: "إنشاء حساب جديد",
    register_name: "الاسم الكامل",
    register_language: "اللغة المفضلة",
    register_submit: "إنشاء الحساب",
    register_has_account: "لديك حساب بالفعل؟",
    register_login_link: "تسجيل الدخول",
    dashboard_welcome: "أهلاً بعودتك",
    dashboard_subtitle: "هذه لمحة عن رحلتك العلاجية.",
    common_loading: "جارٍ التحميل…",
    common_error: "حدث خطأ ما",
    common_save: "حفظ",
    common_cancel: "إلغاء",
    common_submit: "إرسال",
    common_back: "رجوع",
  },
};

const LangContext = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem("sst_lang") || "en");

  useEffect(() => {
    localStorage.setItem("sst_lang", lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const t = useMemo(() => {
    const dict = STRINGS[lang] || STRINGS.en;
    return (key) => dict[key] || STRINGS.en[key] || key;
  }, [lang]);

  const toggleLang = () => setLang((l) => (l === "en" ? "ar" : "en"));

  return <LangContext.Provider value={{ lang, setLang, toggleLang, t }}>{children}</LangContext.Provider>;
}

export function useLang() {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used within LangProvider");
  return ctx;
}
