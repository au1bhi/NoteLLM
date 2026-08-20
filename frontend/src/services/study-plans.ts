import {
  type StudyPlanListItem,
  type StudyPlansPublic,
  StudyPlansService,
  type StudyPlanUpdate,
  type StudyTaskUpdate,
} from "@/client"

export type StudyPlanOverview = StudyPlanListItem
export type StudyPlansResponse = StudyPlansPublic

export const studyPlansApi = {
  list: (notebookId?: string) =>
    StudyPlansService.readStudyPlans({ notebookId }),
  updateTask: (planId: string, taskId: string, requestBody: StudyTaskUpdate) =>
    StudyPlansService.updateStudyTask({ planId, taskId, requestBody }),
  updatePlan: (planId: string, requestBody: StudyPlanUpdate) =>
    StudyPlansService.updateStudyPlan({ planId, requestBody }),
  deletePlan: (planId: string) => StudyPlansService.deleteStudyPlan({ planId }),
}
