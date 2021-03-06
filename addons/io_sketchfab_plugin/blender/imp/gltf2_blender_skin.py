"""
 * ***** BEGIN GPL LICENSE BLOCK *****
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 *
 * Contributor(s): Julien Duroure.
 *
 * ***** END GPL LICENSE BLOCK *****
 """


import bpy
from mathutils import Vector, Matrix, Quaternion
from ..com.gltf2_blender_conversion import *
from ...io.imp.gltf2_io_binary import *

from ..blender_version import Version

class BlenderSkin():

    @staticmethod
    def create_armature(gltf, skin_id, parent):

        pyskin = gltf.data.skins[skin_id]

        if pyskin.name is not None:
            name = pyskin.name
        else:
            name = "Armature_" + str(skin_id)

        armature = bpy.data.armatures.new(name=name)
        obj = bpy.data.objects.new(name=name, object_data=armature)

        if bpy.app.version == (2, 79, 0):
            Version.link(gltf.blender_scene, obj)
        else:
            bpy.context.scene.collection.children[-1].objects.link(obj)

        pyskin.blender_armature_name = obj.name
        if parent is not None:
            obj.parent = bpy.data.objects[gltf.data.nodes[parent].blender_object]


    @staticmethod
    def set_bone_transforms(gltf, skin_id, bone, node_id, parent):

        pyskin = gltf.data.skins[skin_id]
        pynode = gltf.data.nodes[node_id]

        obj   = bpy.data.objects[pyskin.blender_armature_name]

        # Set bone bind_pose by inverting bindpose matrix
        if node_id in pyskin.joints:
            index_in_skel = pyskin.joints.index(node_id)
            inverse_bind_matrices = BinaryData.get_data_from_accessor(gltf, pyskin.inverse_bind_matrices)
            # Needed to keep scale in matrix, as bone.matrix seems to drop it
            if index_in_skel < len(inverse_bind_matrices):
                pynode.blender_bone_matrix = Conversion.matrix_gltf_to_blender(inverse_bind_matrices[index_in_skel]).inverted()
                bone.matrix = pynode.blender_bone_matrix
            else:
                gltf.log.error("Error with inverseBindMatrix for skin " + pyskin)
        else:
            print('No invBindMatrix for bone ' + str(node_id))
            pynode.blender_bone_matrix = Matrix()

        # Parent the bone
        if parent is not None and hasattr(gltf.data.nodes[parent], "blender_bone_name"):
            bone.parent = obj.data.edit_bones[gltf.data.nodes[parent].blender_bone_name] #TODO if in another scene

        # Switch to Pose mode
        bpy.ops.object.mode_set(mode="POSE")
        obj.data.pose_position = 'POSE'

        # Set posebone location/rotation/scale (in armature space)
        # location is actual bone location minus it's original (bind) location
        bind_location = Matrix.Translation(pynode.blender_bone_matrix.to_translation())
        bind_rotation = pynode.blender_bone_matrix.to_quaternion()
        bind_scale = Conversion.scale_to_matrix(pynode.blender_bone_matrix.to_scale())

        location, rotation, scale  = Conversion.matrix_gltf_to_blender(pynode.transform).decompose()
        if parent is not None and hasattr(gltf.data.nodes[parent], "blender_bone_matrix"):
            parent_mat = gltf.data.nodes[parent].blender_bone_matrix

            # Get armature space location (bindpose + pose)
            # Then, remove original bind location from armspace location, and bind rotation
            final_location = ( Version.mat_mult( Version.mat_mult(bind_location.inverted(), parent_mat), Matrix.Translation(location)) ).to_translation()
            obj.pose.bones[pynode.blender_bone_name].location = Version.mat_mult(bind_rotation.inverted().to_matrix().to_4x4(), final_location)

            # Do the same for rotation
            obj.pose.bones[pynode.blender_bone_name].rotation_quaternion = ( Version.mat_mult( Version.mat_mult(bind_rotation.to_matrix().to_4x4().inverted(), parent_mat), rotation.to_matrix().to_4x4()) ).to_quaternion()
            obj.pose.bones[pynode.blender_bone_name].scale = ( Version.mat_mult( Version.mat_mult(bind_scale.inverted(),parent_mat), Conversion.scale_to_matrix(scale)) ).to_scale()
        else:
            obj.pose.bones[pynode.blender_bone_name].location = Version.mat_mult(bind_location.inverted(), location)
            obj.pose.bones[pynode.blender_bone_name].rotation_quaternion = Version.mat_mult(bind_rotation.inverted(), rotation)
            obj.pose.bones[pynode.blender_bone_name].scale = Version.mat_mult(bind_scale.inverted(), scale)

    @staticmethod
    def create_bone(gltf, skin_id, node_id, parent):

        pyskin = gltf.data.skins[skin_id]
        pynode = gltf.data.nodes[node_id]

        scene = bpy.data.scenes[gltf.blender_scene]
        obj   = bpy.data.objects[pyskin.blender_armature_name]

        Version.set_scene(scene)
        Version.set_active_object(obj)
        bpy.ops.object.mode_set(mode="EDIT")

        if pynode.name:
            name = pynode.name
        else:
            name = "Bone_" + str(node_id)

        bone = obj.data.edit_bones.new(name=name)
        pynode.blender_bone_name = bone.name
        pynode.blender_armature_name = pyskin.blender_armature_name
        bone.tail = Vector((0.0,1.0,0.0)) # Needed to keep bone alive

        # set bind and pose transforms
        BlenderSkin.set_bone_transforms(gltf, skin_id, bone, node_id, parent)
        bpy.ops.object.mode_set(mode="OBJECT")

    @staticmethod
    def create_vertex_groups(gltf, skin_id):
        pyskin = gltf.data.skins[skin_id]
        for node_id in pyskin.node_ids:
            obj = bpy.data.objects[gltf.data.nodes[node_id].blender_object]
            for bone in pyskin.joints:
                obj.vertex_groups.new(name=gltf.data.nodes[bone].blender_bone_name)

    @staticmethod
    def assign_vertex_groups(gltf, skin_id):
        pyskin = gltf.data.skins[skin_id]
        for node_id in pyskin.node_ids:
            node = gltf.data.nodes[node_id]
            obj = bpy.data.objects[node.blender_object]

            offset = 0
            for prim in gltf.data.meshes[node.mesh].primitives:
                idx_already_done = {}

                if 'JOINTS_0' in prim.attributes.keys() and 'WEIGHTS_0' in prim.attributes.keys():
                    joint_ = BinaryData.get_data_from_accessor(gltf, prim.attributes['JOINTS_0'])
                    weight_ = BinaryData.get_data_from_accessor(gltf, prim.attributes['WEIGHTS_0'])

                    for poly in obj.data.polygons:
                        for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                            vert_idx = obj.data.loops[loop_idx].vertex_index

                            if vert_idx in idx_already_done.keys():
                                continue
                            idx_already_done[vert_idx] = True

                            if vert_idx in range(offset, offset + prim.vertices_length):

                                tab_index = vert_idx - offset
                                cpt = 0
                                for joint_idx in joint_[tab_index]:
                                    weight_val = weight_[tab_index][cpt]
                                    if weight_val != 0.0:   # It can be a problem to assign weights of 0
                                                            # for bone index 0, if there is always 4 indices in joint_ tuple
                                        group = obj.vertex_groups[gltf.data.nodes[pyskin.joints[joint_idx]].blender_bone_name]
                                        group.add([vert_idx], weight_val, 'REPLACE')
                                    cpt += 1
                else:
                    gltf.log.error("No Skinning ?????") #TODO


            offset = offset + prim.vertices_length

    @staticmethod
    def create_armature_modifiers(gltf, skin_id):

        pyskin = gltf.data.skins[skin_id]

        if pyskin.blender_armature_name is None:
            # TODO seems something is wrong
            # For example, some joints are in skin 0, and are in another skin too
            # Not sure this is glTF compliant, will check it
            return

        for node_id in pyskin.node_ids:
            node = gltf.data.nodes[node_id]
            obj = bpy.data.objects[node.blender_object]

            for obj_sel in bpy.context.scene.objects:
                Version.deselect(obj_sel)
            Version.select(obj)
            Version.set_active_object(obj)

            #bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
            #obj.parent = bpy.data.objects[pyskin.blender_armature_name]
            arma = obj.modifiers.new(name="Armature", type="ARMATURE")
            arma.object = bpy.data.objects[pyskin.blender_armature_name]
