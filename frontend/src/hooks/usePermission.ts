import { useOrg } from "@/context/OrgContext";

export function usePermission() {
  const { isAdmin, activeOrg } = useOrg();
  return {
    canEdit: isAdmin,
    canInvite: isAdmin,
    hasOrg: activeOrg !== null,
  };
}
