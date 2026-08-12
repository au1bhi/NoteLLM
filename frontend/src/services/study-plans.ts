import {
  type StudyPlanListItem,
  type StudyPlansPublic,
  StudyPlansService,
} from "@/client"

export type StudyPlanOverview = StudyPlanListItem
export type StudyPlansResponse = StudyPlansPublic

export const studyPlansApi = {
  list: (notebookId?: string) =>
    StudyPlansService.readStudyPlans({ notebookId }),
}
