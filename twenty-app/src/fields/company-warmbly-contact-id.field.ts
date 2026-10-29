import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

export default defineField({
  universalIdentifier: '3af66444-daa9-4b59-be9e-a281e0c2465e',
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'warmblyContactId',
  type: FieldType.TEXT,
  label: 'Warmbly contact',
  description: 'Id of the linked Warmbly contact; written by crm-sync',
  icon: 'IconLink',
});
