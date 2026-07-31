import { Quote, Search, ShieldCheck } from "lucide-react"

import { Appearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import { Footer } from "./Footer"

interface AuthLayoutProps {
  children: React.ReactNode
}

const FEATURES = [
  {
    icon: Search,
    title: "限定资料问答",
    description: "回答只基于你上传到笔记本中的内容。",
  },
  {
    icon: Quote,
    title: "可追溯引用",
    description: "每条答案都附上来源、页码与原文摘录。",
  },
  {
    icon: ShieldCheck,
    title: "数据隔离",
    description: "每个账户的笔记本、资料与会话彼此隔离。",
  },
]

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-brand-gradient text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 -top-24 size-96 rounded-full bg-white/10 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-32 right-0 size-96 rounded-full bg-white/10 blur-3xl"
        />
        <div className="relative z-10">
          <Logo variant="full" monochrome asLink={false} />
        </div>

        <div className="relative z-10 max-w-md">
          <h2 className="text-3xl font-semibold tracking-tight">
            把资料变成带可追溯引用的问答
          </h2>
          <ul className="mt-9 space-y-5">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="flex gap-3.5">
                <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/15">
                  <feature.icon className="size-4" />
                </span>
                <div>
                  <p className="font-medium">{feature.title}</p>
                  <p className="mt-0.5 text-sm text-white/75">
                    {feature.description}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-sm text-white/70">
          NoteLLM — 面向个人学习与研究的文档问答系统
        </p>
      </div>

      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex items-center justify-between">
          <Logo variant="full" asLink={false} className="lg:hidden" />
          <Appearance />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-sm">{children}</div>
        </div>
        <Footer />
      </div>
    </div>
  )
}
