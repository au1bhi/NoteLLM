import {
  type StudyPlanAiAdjustRequest,
  type StudyPlanListItem,
  type StudyPlansPublic,
  StudyPlansService,
  type StudyPlanUpdate,
  type StudyTaskCreate,
  type StudyTaskUpdate,
} from "@/client"

export type StudyPlanOverview = StudyPlanListItem
export type StudyPlansResponse = StudyPlansPublic

export const studyPlansApi = {
  list: (notebookId?: string) =>
    StudyPlansService.readStudyPlans({ notebookId }),
  updatePlan: (planId: string, requestBody: StudyPlanUpdate) =>
    StudyPlansService.updateStudyPlan({ planId, requestBody }),
  deletePlan: (planId: string) => StudyPlansService.deleteStudyPlan({ planId }),
  createTask: (planId: string, requestBody: StudyTaskCreate) =>
    StudyPlansService.createStudyTask({ planId, requestBody }),
  updateTask: (planId: string, taskId: string, requestBody: StudyTaskUpdate) =>
    StudyPlansService.updateStudyTask({ planId, taskId, requestBody }),
  deleteTask: (planId: string, taskId: string) =>
    StudyPlansService.deleteStudyTask({ planId, taskId }),
  aiAdjust: (planId: string, requestBody: StudyPlanAiAdjustRequest) =>
    StudyPlansService.aiAdjustPlan({ planId, requestBody }),
}
